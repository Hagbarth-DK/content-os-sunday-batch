"""Erstat CTA-beatet i en Metode C-video med et klip, hvor avataren selv læser CTA-sætningen (create_video_from_avatar med script).
Grund (21/11-2026): create_speech (HeyGen Voice) udtaler START forkert; avatarens egen oplæsning udtaler det rigtigt.
Brug: python3 tools/ny_cta.py mappe cta_start klip.mp4 beatNN  (mappe har config.json, tale.mp3, tale.srt og av/). Skriver tale2.mp3, tale2.srt og ud2.mp4."""
import sys,subprocess,re,shutil,os
# brug: ny_cta.py mappe cta_start klip.mp4 beatNN
d,cs,klip,beat=sys.argv[1],float(sys.argv[2]),sys.argv[3],sys.argv[4]
dur=lambda p: float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',p]))
old_tot=dur(f'{d}/tale.mp3'); new_len=dur(klip); old_len=old_tot-cs; k=new_len/old_len
subprocess.run(['ffmpeg','-v','error','-y','-i',f'{d}/tale.mp3','-i',klip,'-filter_complex',
 f'[0:a]atrim=0:{cs},asetpts=PTS-STARTPTS,aresample=44100[a];[1:a]aresample=44100,asetpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=0:a=1[o]','-map','[o]','-c:a','libmp3lame','-b:a','192k',f'{d}/tale2.mp3'],check=True)
def ts(s):
    h,m,r=s.split(':');sec,ms=r.split(',');return int(h)*3600+int(m)*60+int(sec)+int(ms)/1000
def t(s):
    ms=int(round(s*1000));h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s_,ms=divmod(ms,1000);return f"{h:02d}:{m:02d}:{s_:02d},{ms:03d}"
out=[]
for b in open(f'{d}/tale.srt',encoding='utf-8').read().strip().split('\n\n'):
    l=b.splitlines(); a,c=[ts(x.strip()) for x in l[1].split('-->')]
    if a>=cs: a=cs+(a-cs)*k; c=cs+(c-cs)*k
    out.append(f"{l[0]}\n{t(a)} --> {t(c)}\n{l[2]}\n")
open(f'{d}/tale2.srt','w',encoding='utf-8').write('\n'.join(out))
shutil.copy(klip,f'{d}/av/{beat}.mp4')
r=subprocess.run(['python3','os.path.join(os.path.dirname(os.path.abspath(__file__)),'byg_reel.py')',f'{d}/config.json',f'{d}/tale2.mp3',f'{d}/tale2.srt',f'{d}/ud2.mp4','--av-mappe',f'{d}/av/'],capture_output=True,text=True)
print(r.stdout[-900:],r.stderr[-500:]); print('gammel',round(old_len,2),'ny',round(new_len,2))
