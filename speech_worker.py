"""Offline transcription and local Piper fallback; JSON stdin/stdout."""
import json
import sys
from pathlib import Path

def transcription(segments):
    segments=list(segments)
    text=' '.join(segment.text.strip() for segment in segments).strip()
    words=[word for segment in segments for word in (segment.words or []) if word.word.strip()]
    confidence=sum(word.probability for word in words)/len(words) if words else None
    uncertain=bool(text) and (not words or confidence<.55 or any(segment.avg_logprob<-.9 for segment in segments))
    return {'text':text,'uncertain':uncertain,'confidence':round(confidence,3) if confidence is not None else None}

def main(job):
    storage=Path(job['storage_dir'])
    if job['operation']=='transcribe':
        from faster_whisper import WhisperModel
        model=WhisperModel(str(storage/'models/whisper-small'),device='cpu',compute_type='int8',cpu_threads=8,local_files_only=True)
        segments,info=model.transcribe(job['path'],language='es',vad_filter=True,beam_size=3,
                                       word_timestamps=True,condition_on_previous_text=False,
                                       initial_prompt='Asistente Jarvis, español de Argentina. Programación, física, matemática y trabajo.')
        print(json.dumps(transcription(segments),ensure_ascii=False))
    else:
        import sherpa_onnx
        import soundfile as sf
        folder=storage/'models/vits-piper-es_MX-ald-medium'
        model=next(folder.glob('*.onnx'))
        config=sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(model),tokens=str(folder/'tokens.txt'),data_dir=str(folder/'espeak-ng-data')),
            num_threads=4,provider='cpu'),max_num_sentences=2)
        tts=sherpa_onnx.OfflineTts(config)
        audio=tts.generate(job['text'],sid=0,speed=.95)
        sf.write(job['path'],audio.samples,audio.sample_rate,subtype='PCM_16')
        print(json.dumps({'path':job['path']}))

if __name__=='__main__':main(json.load(sys.stdin))
