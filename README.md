# Empire Reels AI

Editor audiovisual local de **automatizadosai.es**. Transcribe un vídeo real en español, analiza escenas y caras, crea planes JSON y renderiza versiones verticales con FFmpeg.

## Estado real

Este repositorio contiene el motor en desarrollo, utilizable por línea de comandos. No contiene todavía un dashboard web, subida desde navegador, autenticación ni un servicio SaaS desplegado.

Los diez estilos incluyen viral, empresarial, cinematográfico, storytelling, educativo, podcast, ventas, minimalista, humor y retención. La selección por defecto es heurística; se puede configurar un modelo local en Ollama para refinarla. No se promete viralidad. Los vídeos cortos también pueden recortarse con la configuración automática actual.

Se han procesado vídeos reales y validado MP4 verticales en el equipo de desarrollo. Los vídeos y datos privados no se distribuyen. Las composiciones gráficas personalizadas del vídeo promocional se hicieron con scripts específicos y todavía no forman parte del flujo genérico.

## Instalación

Requisitos: Python 3.11, FFmpeg y FFprobe disponibles en PATH, FFmpeg con libass y fuentes. Windows o Linux. Para CPU se recomienda limitar los procesos concurrentes; una GPU NVIDIA es opcional.

Desde la raíz:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_assets.py
Copy-Item .env.example .env
.\.venv\Scripts\python.exe empire.py "C:\ruta\mi_video.mp4"
```

En Linux, usa `.venv/bin/python` y `cp .env.example .env`.

El primer análisis descarga el modelo Whisper. El archivo audiovisual se procesa localmente. Si activas un proveedor externo, se transmite el contenido requerido por esa integración: consulta configuración y código antes de habilitarlo.

```powershell
.\.venv\Scripts\python.exe empire.py "C:\ruta\mi_video.mp4" --style viral --preview
.\.venv\Scripts\python.exe empire.py "C:\ruta\mi_video.mp4" --duration 45
.\.venv\Scripts\python.exe empire.py "C:\ruta\mi_video.mp4" --analyze-only
```

Resultados en `data/projects/<hash>/`: análisis compartido, planes por estilo, MP4, SRT, estados individuales y ZIP con los resultados correctos. Un fallo devuelve un código distinto de cero y conserva el análisis para reintentarlo.

## Configuración

Las variables usan el prefijo `ER_` (ver `backend/.env.example`). Whisper y FFmpeg funcionan sin una API de pago. Pexels/Pixabay y los proveedores editoriales externos son opcionales. Las claves se guardan localmente; nunca las incluyas en commits.

## Limitaciones y próximos pasos

- Interfaz web y cola de trabajos persistente todavía pendientes.
- Preservar automáticamente toda la duración de vídeos cortos todavía pendiente.
- HDR requiere tratamiento específico: el render genérico aún no integra la conversión HLG utilizada en el clip promocional.
- B-roll de stock: integraciones presentes, sin prueba autenticada con claves en esta entrega.
- Generación de imágenes IA, diapositivas y marca de agua universal: pendientes de integrar en el flujo genérico.
- Diarización, editor visual, S3, cuotas, usuarios y despliegue: pendientes.
- Validación de códecs y volumen no sustituye la revisión editorial y visual.

## Recursos y derechos

Las tipografías y YuNet se descargan desde sus repositorios upstream con sus respectivas licencias mediante `setup_assets.py`. No se incluyen medios personales. No se ha asignado una licencia de distribución al código; el repositorio privado no concede derechos de reutilización automáticamente.

