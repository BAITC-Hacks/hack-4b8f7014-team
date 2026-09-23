# Локальные модели и доступ

Текущий начальный профиль: Whisper small (multilingual, CPU int8), Qwen2.5 7B
Q4_K_M через Ollama, pyannote Community-1. Whisper small выбран для первого запуска
на ноутбуке с 16 ГБ RAM; теперь small остаётся запасным вариантом. Сравнение с large-v3: [STT_EVALUATION.md](STT_EVALUATION.md).
Файлы весов и runtime остаются в игнорируемых `models/` и `data/`, не в Git.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
.\.venv\Scripts\python.exe -m scripts.setup_models whisper
```

Для Community-1 нужно самостоятельно войти на
[страницу модели](https://huggingface.co/pyannote/speaker-diarization-community-1),
принять условия доступа и создать токен чтения в настройках Hugging Face.
Введите его только в локальный терминал, не в чат, README или Git:

```powershell
.\.venv\Scripts\hf.exe auth login
.\.venv\Scripts\python.exe -m scripts.setup_models diarization
```

Токен используется только для предварительного скачивания. Во время обработки
`HF_HUB_OFFLINE=1`; облачная обработка не используется.

Портативный Ollama: распакуйте официальный `ollama-windows-amd64.zip` из
[релизов Ollama](https://github.com/ollama/ollama/releases) в `data/runtime/ollama`.
Перед запуском сервера установите `OLLAMA_MODELS` в абсолютный путь `models/ollama`,
`OLLAMA_HOST=127.0.0.1:11434`, `OLLAMA_NO_CLOUD=1`, затем выполните
`ollama.exe serve` и в другом терминале `ollama.exe pull qwen2.5:7b`.
После подготовки можно запускать `scripts/start-local.ps1`.

В `.env`: `MINUTES_OLLAMA_MODEL=qwen2.5:7b`, CPU/int8 по умолчанию.
Путь к FFmpeg можно получить командой
`python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"`
и сохранить в `MINUTES_FFMPEG`. Для pyannote Windows при проблемах torchcodec
используйте загрузку подготовленного WAV в память (адаптер проекта).

Подготовка требует интернета. После скачивания весов работа должна быть локальной.
Наличие моделей не гарантирует качество: нужны реальные RU/KZ/смешанные записи
с ручной разметкой. Начальный синтетический тест не является такой оценкой.

## Проверено 23 сентября 2026

Windows, Python 3.12, 16 ГБ RAM, RTX 4060 Laptop 8 ГБ. Установлены FFmpeg через
imageio-ffmpeg, faster-whisper, Ollama 0.34.3, Qwen2.5 7B Q4_K_M и pyannote.audio.
Whisper small на CPU распознал 19-секундную синтетическую запись; имя Айдана
распознано как Айдена. Qwen 7B извлекла два поручения и даты 2026-09-25/2026-09-30,
но имя требует ручной проверки. Qwen 3B в первом прогоне пропустила сроки.
Позднее выполнена небольшая проверка RU/KZ на FLEURS; смешанная речь пока не оценена.

Community-1 скачана после авторизации, revision
`3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`. Полный прогон через API и worker
успешно выполнен на двух синтетических русских записях: 19 секунд с одним голосом
и 27 секунд с двумя голосами. Во втором примере диаризация вернула SPEAKER_00,
SPEAKER_01, SPEAKER_00 в ожидаемой последовательности. Найдены два поручения:
договор для Тимура до 2026-09-30 и отчёт для Айданы (распознано «Айдена») до
2026-09-25. Оба экспорта через API вернули 200 и непустые DOCX/PDF.
Это функциональный smoke test, не оценка точности на реальных совещаниях.
`requirements-windows-tested.txt` фиксирует установленное Windows-окружение,
но не утверждает совместимость всех пакетов с Linux или другими версиями Python.
Для воспроизведения частичной проверки: `scripts/make_test_audio.ps1`,
затем `python -m scripts.smoke_local`. Скрипт выполняет настоящий STT и запрос
локального LLM; диаризацию он не проверяет. Ни записи, ни веса, ни токены не коммитятся.

## Более точный STT: large-v3

```powershell
python -m scripts.setup_models whisper-large-v3
```

В `.env`: `MINUTES_STT_MODEL_DIR=./models/whisper-large-v3`.
На CPU оставьте `MINUTES_DEVICE=cpu` и `MINUTES_COMPUTE_TYPE=int8`.
Для NVIDIA на Windows дополнительно установите `requirements-gpu-windows.txt`,
задайте `MINUTES_STT_DEVICE=cuda` и `MINUTES_STT_COMPUTE_TYPE=int8_float16`.
Установленные DLL подключаются внутри процесса, системный PATH не изменяется.
`MINUTES_DEVICE=cpu` сохраняет pyannote на процессоре; CUDA-версия Torch для
такого сочетания не нужна. После изменения `.env` перезапустите worker/API.
Веса small сохраняются для возврата к прежнему профилю.

Профиль large-v3 CUDA проверен на этом ноутбуке: RTX 4060 Laptop 8 ГБ,
CTranslate2 4.8.2, cuBLAS 12.4.5.8, cuDNN 9.1.0.70; pyannote на CPU.
Полный прогон записи 27 секунд с двумя голосами завершился, получены два
поручения с подтверждёнными цитатами, DOCX/PDF возвращают 200.
Последовательность голосов сохранена (00/01/00), но два промежуточных фрагмента
остались без уверенного говорящего — улучшение STT не устраняет проблему диаризации.
При этом профиле Ollama выгружает модель после ответа, чтобы освободить видеопамять
для следующей записи. Закройте сторонние GPU-нагрузки, если возникает нехватка памяти.
