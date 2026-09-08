import asyncio, os, shutil, subprocess, tempfile
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands
TOKEN=os.getenv('DISCORD_TOKEN'); MAX_FILE_SIZE=25*1024*1024
EXT={'.mp3','.wav','.m4a','.flac','.ogg','.aac','.opus'}
intents=discord.Intents.default(); intents.message_content=True
class AudioBot(commands.Bot):
    async def setup_hook(self): await self.tree.sync()
bot=AudioBot(command_prefix='!',intents=intents)
def ffmpeg(args):
    if not shutil.which('ffmpeg'): raise RuntimeError('FFmpeg fehlt: sudo apt install ffmpeg')
    p=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',*map(str,args)],capture_output=True,text=True)
    if p.returncode: raise RuntimeError(p.stderr[-1600:] or 'FFmpeg-Fehler')
def duration(p):
    x=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(p)],capture_output=True,text=True)
    try:return max(1,float(x.stdout.strip()))
    except:return 180.0
def analyse(p):
    try:
        import librosa
        y,sr=librosa.load(p,sr=22050,mono=True,duration=180)
        t,_=librosa.beat.beat_track(y=y,sr=sr); t=float(t[0] if hasattr(t,'__len__') else t)
        c=librosa.feature.chroma_cqt(y=y,sr=sr).mean(axis=1)
        return {'bpm':max(60,min(180,t or 120)),'key':int(c.argmax())}
    except Exception:return {'bpm':120.0,'key':0}
def master_filter(bass='mittel',loud='normal'):
    bg={'wenig':-1,'mittel':1.5,'viel':4}[bass]; target={'leise':-18,'normal':-14,'laut':-10}[loud]
    return f'highpass=f=28,lowpass=f=19500,equalizer=f=55:t=q:w=0.8:g={bg},equalizer=f=250:t=q:w=1:g=-2,equalizer=f=2500:t=q:w=1:g=1.5,acompressor=threshold=-24dB:ratio=2.2:attack=18:release=160:makeup=1,stereotools=mlev=1.02:slev=1.02,alimiter=limit=0.96:attack=5:release=90,loudnorm=I={target}:TP=-1.2:LRA=9'
def render_master(src,out,bass,loud): ffmpeg(['-i',src,'-vn','-af',master_filter(bass,loud),'-map_metadata','0','-c:a','libmp3lame','-b:a','320k',out])
def render_remix(a,b,out,bass,loud,mode):
    A=analyse(a); B=analyse(b); bpm=(A['bpm']+B['bpm'])/2; phrase=max(8,min(32,round(8*60/bpm,2))); fade=min(8,phrase/2); da=duration(a); db=duration(b)
    if mode=='transition': al=min(da,max(phrase*8,60)); bl=min(db,max(phrase*12,90))
    elif mode=='beat': al=min(da,phrase*8); bl=min(db,phrase*8)
    else: al=min(da,phrase*8); bl=min(db,phrase*16)
    start=max(0,db-bl)
    fc=f'[0:a]atrim=0:{al},asetpts=PTS-STARTPTS[a];[1:a]atrim={start}:{start+bl},asetpts=PTS-STARTPTS[b];[a][b]acrossfade=d={fade}:c1=tri:c2=tri,{master_filter(bass,loud)}[o]'
    ffmpeg(['-i',a,'-i',b,'-filter_complex',fc,'-map','[o]','-c:a','libmp3lame','-b:a','320k',out])
async def save(att,path):
    if att.size>MAX_FILE_SIZE: raise RuntimeError('Maximal 25 MB pro Datei.')
    if Path(att.filename).suffix.lower() not in EXT: raise RuntimeError('Nicht unterstütztes Audioformat.')
    await att.save(path)
def choices(xs): return [app_commands.Choice(name=x.capitalize(),value=x) for x in xs]
@bot.tree.command(name='master',description='Song automatisch analysieren und mastern')
@app_commands.describe(audio='Audiodatei',bass='Bass',lautstaerke='Lautstärke')
@app_commands.choices(bass=choices(['wenig','mittel','viel']),lautstaerke=choices(['leise','normal','laut']))
async def master(i:discord.Interaction,audio:discord.Attachment,bass:app_commands.Choice[str],lautstaerke:app_commands.Choice[str]):
    await i.response.defer()
    try:
        with tempfile.TemporaryDirectory() as d:
            d=Path(d); src=d/('in'+Path(audio.filename).suffix.lower()); out=d/'mastered.mp3'; await save(audio,src); await asyncio.to_thread(render_master,src,out,bass.value,lautstaerke.value); await i.followup.send('✅ Analyse + Mastering fertig.',file=discord.File(out,'mastered.mp3'))
    except Exception as e: await i.followup.send(f'❌ `{e}`')
@bot.tree.command(name='remix',description='Beat-orientierter Remix mit analysierten Songabschnitten')
@app_commands.describe(first='Song 1',second='Song 2',bass='Bass',lautstaerke='Lautstärke',modus='Modus')
@app_commands.choices(bass=choices(['wenig','mittel','viel']),lautstaerke=choices(['leise','normal','laut']),modus=choices(['mashup','transition','beat']))
async def remix(i:discord.Interaction,first:discord.Attachment,second:discord.Attachment,bass:app_commands.Choice[str],lautstaerke:app_commands.Choice[str],modus:app_commands.Choice[str]):
    await i.response.defer()
    try:
        with tempfile.TemporaryDirectory() as d:
            d=Path(d); a=d/('a'+Path(first.filename).suffix.lower()); b=d/('b'+Path(second.filename).suffix.lower()); out=d/'remix.mp3'; await save(first,a); await save(second,b); await asyncio.to_thread(render_remix,a,b,out,bass.value,lautstaerke.value,modus.value); await i.followup.send('🔥 Analyse + Beatmatching + Arrangement + Übergang + Mastering fertig.',file=discord.File(out,'remix.mp3'))
    except Exception as e: await i.followup.send(f'❌ `{e}`')
@bot.command()
async def ping(ctx): await ctx.send('Pong! Audio-Bot ist online.')
if not TOKEN: raise RuntimeError('DISCORD_TOKEN fehlt als Umgebungsvariable.')
bot.run(TOKEN)
