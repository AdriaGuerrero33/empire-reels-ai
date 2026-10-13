"""Download public upstream assets; never upload local media or API keys."""
from pathlib import Path
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent / 'app' / 'assets'

def download(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    with urlopen(Request(url, headers={'User-Agent': 'EmpireReelsAI/0.1'}), timeout=60) as response:
        data = response.read()
    if len(data) < 100:
        raise RuntimeError(f'Invalid asset: {destination.name}')
    destination.write_bytes(data)
    print(destination.name)

def main():
    zoo='https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_detection_yunet'
    download('https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx', BASE/'models'/'face_detection_yunet_2023mar.onnx')
    download(zoo+'/LICENSE', BASE/'models'/'LICENSE-YuNet.txt')
    fonts={'anton':['Anton-Regular.ttf'], 'bebasneue':['BebasNeue-Regular.ttf'],
           'bangers':['Bangers-Regular.ttf'], 'archivoblack':['ArchivoBlack-Regular.ttf'],
           'poppins':['Poppins-Medium.ttf','Poppins-SemiBold.ttf','Poppins-Bold.ttf','Poppins-ExtraBold.ttf','Poppins-Black.ttf'],
           'dmserifdisplay':['DMSerifDisplay-Regular.ttf','DMSerifDisplay-Italic.ttf'],
           'lato':['Lato-Light.ttf','Lato-Regular.ttf','Lato-Bold.ttf']}
    for family, names in fonts.items():
        url=f'https://raw.githubusercontent.com/google/fonts/main/ofl/{family}'
        for name in names:
            download(url+'/'+name, BASE/'fonts'/name)
        download(url+'/OFL.txt', BASE/'fonts'/f'LICENSE-{family}.txt')
    for family, name in [('luckiestguy','LuckiestGuy-Regular.ttf'),('permanentmarker','PermanentMarker-Regular.ttf')]:
        url=f'https://raw.githubusercontent.com/google/fonts/main/apache/{family}'
        download(url+'/'+name,BASE/'fonts'/name)
        download(url+'/LICENSE.txt',BASE/'fonts'/f'LICENSE-{family}.txt')

if __name__=='__main__':
    main()

