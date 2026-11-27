"""Offline Qwen3-TTS voice cloning from a reusable CPU prompt."""
import argparse
from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile

from owned_voice_service import block_external_network, serve

ENGINE = 'Qwen3-TTS-12Hz-1.7B-Base'
MODEL = None


def load_model(storage):
    global MODEL
    if MODEL is None:
        import torch
        from qwen_tts import Qwen3TTSModel
        if not torch.cuda.is_available():
            raise RuntimeError('Este motor de voz requiere una GPU CUDA.')
        torch.set_num_threads(6)
        MODEL = Qwen3TTSModel.from_pretrained(
            str(storage / 'models/qwen3-tts-1.7b-base'), device_map='cuda:0',
            dtype=torch.float16, attn_implementation='sdpa', local_files_only=True)
    return MODEL


def generate(storage, text, profile_path=None):
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts.inference.qwen3_tts_model import VoiceClonePromptItem
    profile = profile_path or storage / 'models/jarvis-owned/voice.pth'
    saved = torch.load(profile, map_location='cpu', weights_only=True)
    items = saved['items']
    if len(items) != 1 or not items[0]['icl_mode'] or items[0]['x_vector_only_mode']:
        raise ValueError('El perfil local Qwen no es válido.')
    prompt = [VoiceClonePromptItem(**items[0])]
    with torch.inference_mode():
        audio, rate = load_model(storage).generate_voice_clone(text=text, language='Spanish', voice_clone_prompt=prompt, max_new_tokens=1000)
    if rate != 24000 or not len(audio[0]) or not np.isfinite(audio[0]).all():
        raise ValueError('El modelo no produjo audio válido.')
    stream = io.BytesIO()
    sf.write(stream, audio[0], rate, format='WAV', subtype='PCM_16')
    return stream.getvalue()


FAST_MODEL = None


def pcm_chunks(storage, text):
    global FAST_MODEL
    import numpy as np
    import torch
    from faster_qwen3_tts import FasterQwen3TTS
    from qwen_tts.inference.qwen3_tts_model import VoiceClonePromptItem

    if FAST_MODEL is None:
        torch.set_num_threads(6)
        FAST_MODEL = FasterQwen3TTS.from_pretrained(
            str(storage / 'models/qwen3-tts-1.7b-base'), device='cuda:0',
            dtype=torch.float16, max_seq_len=2048, local_files_only=True)
        # The residual codebooks inherit their sampling policy at graph capture.
        FAST_MODEL.predictor_graph.do_sample = False
    profile = storage / 'models/jarvis-owned/voice.pth'
    items = torch.load(profile, map_location='cpu', weights_only=True)['items']
    if len(items) != 1 or not items[0]['icl_mode'] or items[0]['x_vector_only_mode']:
        raise ValueError('El perfil Qwen no es válido.')
    prompt = [VoiceClonePromptItem(**items[0])]
    with torch.inference_mode():
        for block, rate, _ in FAST_MODEL.generate_voice_clone_streaming(
                text=text, language='Spanish', voice_clone_prompt=prompt, chunk_size=6,
                max_new_tokens=1000, non_streaming_mode=True, do_sample=False):
            if rate != 24000 or not np.isfinite(block).all():
                raise ValueError('Bloque de audio local no válido.')
            if block.size:
                yield np.rint(np.clip(block, -1, 1) * 32767).astype('<i2').tobytes()


def render_wav(storage, text):
    import wave
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        for block in pcm_chunks(storage, text):
            wav.writeframesraw(block)
    return stream.getvalue()


def prepare(storage, reference, transcript):
    import numpy as np
    import soundfile as sf
    import torch
    from owned_voice import SAMPLE_PHRASE
    text = transcript.read_text(encoding='utf-8-sig').strip()
    if not text:
        raise ValueError('La transcripción está vacía.')
    with sf.SoundFile(reference) as source:
        rate = source.samplerate
        blocks = []
        count = 0
        for block in source.blocks(blocksize=32768, dtype='float32', always_2d=True):
            count += len(block)
            if count > rate * 60:
                raise ValueError('La referencia debe durar hasta un minuto.')
            blocks.append(block.mean(axis=1))
    if count < rate * 3:
        raise ValueError('La referencia debe durar al menos tres segundos.')
    audio = np.concatenate(blocks)
    if not np.isfinite(audio).all():
        raise ValueError('La referencia contiene audio inválido.')
    with torch.inference_mode():
        items = load_model(storage).create_voice_clone_prompt(ref_audio=(audio, rate), ref_text=text, x_vector_only_mode=False)
    tensors = [{k: v.detach().cpu() if isinstance(v,torch.Tensor) else v for k,v in asdict(i).items()} for i in items]
    reference_hash = hashlib.sha256(reference.read_bytes()).hexdigest()
    target = storage / 'models/jarvis-owned'
    (target/'samples').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target) as temp:
        stage = Path(temp)
        profile = stage/'voice.pth'
        torch.save({'items':tensors,'reference_sha256':reference_hash}, profile)
        demo = stage/'demo.wav'
        demo.write_bytes(generate(storage,SAMPLE_PHRASE,profile))
        state = dict(engine=ENGINE, prepared=True, approved=False, reference_sha256=reference_hash,
                     model_revision=json.loads((Path(__file__).parent/'qwen-voice-weights.json').read_text())['revision'],
                     profile_sha256=hashlib.sha256(profile.read_bytes()).hexdigest(),
                     sample_sha256=hashlib.sha256(demo.read_bytes()).hexdigest(), sample_phrase=SAMPLE_PHRASE)
        manifest=stage/'profile.json'
        manifest.write_text(json.dumps(state,ensure_ascii=False),encoding='utf8')
        profile.replace(target/'voice.pth')
        demo.replace(target/'samples/demo.wav')
        manifest.replace(target/'profile.json')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--storage',type=Path)
    p.add_argument('--serve',action='store_true')
    p.add_argument('--reference',type=Path)
    p.add_argument('--transcript',type=Path)
    args=p.parse_args()
    storage=args.storage or Path(os.environ['JARVIS_OWNED_STORAGE'])
    sys.path.insert(0,str(storage/'tools/qwen-voice-packages'))
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    block_external_network()
    if args.serve:serve(storage,engine=ENGINE,synthesize=render_wav,is_loaded=lambda:FAST_MODEL is not None,streamer=pcm_chunks)
    elif args.reference and args.transcript:prepare(storage,args.reference,args.transcript)
    else:p.error('Se requieren --reference y --transcript para preparar el perfil.')
