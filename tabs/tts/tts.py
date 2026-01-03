import json
import os
import random
import sys

import gradio as gr

now_dir = os.getcwd()
sys.path.append(now_dir)

from assets.i18n.i18n import I18nAuto
from core import run_tts_script, run_srt_tts_script
from tabs.settings.sections.filter import get_filter_trigger, load_config_filter
from tabs.inference.inference import (
    change_choices,
    create_folder_and_move_files,
    get_files,
    get_speakers_id,
    match_index,
    refresh_embedders_folders,
    extract_model_and_epoch,
    default_weight,
    filter_dropdowns,
    update_filter_visibility,
)
from rvc.lib.tools.tts_cache import (
    clear_all_caches,
    get_cache_stats,
    CACHE_DIR,
    OUTPUT_CACHE_DIR,
)

i18n = I18nAuto()

# Azure API 全局开关
AZURE_TTS_ENABLED = os.environ.get("ENABLE_AZURE_TTS_API", "false").lower() == "true"
AZURE_SPEECH_KEY = os.environ.get("AZURE_SPEECH_KEY", "")
DEFAULT_TTS_VOICE = os.environ.get("DEFAULT_TTS_VOICE", "zh-CN-YunxiNeural")


with open(
    os.path.join("rvc", "lib", "tools", "tts_voices.json"), "r", encoding="utf-8"
) as file:
    tts_voices_data = json.load(file)

short_names = [voice.get("ShortName", "") for voice in tts_voices_data]


def process_input(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            file.read()
        gr.Info(f"The file has been loaded!")
        return file_path, file_path
    except UnicodeDecodeError:
        gr.Info(f"The file has to be in UTF-8 encoding.")
        return None, None


def process_srt_input(file_path):
    """Process uploaded SRT file."""
    if file_path and file_path.endswith(".srt"):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                file.read()
            gr.Info("SRT file loaded successfully!")
            return file_path, file_path
        except UnicodeDecodeError:
            gr.Info("The SRT file must be in UTF-8 encoding.")
            return None, None
    return None, None


def check_azure_api_status(use_azure):
    """Check Azure API availability and return status message."""
    if use_azure:
        speech_key = os.environ.get("AZURE_SPEECH_KEY", "")
        service_region = os.environ.get("AZURE_SERVICE_REGION", "")
        if speech_key and service_region:
            return "✅ Azure API enabled. Timing sync is active."
        else:
            return "⚠️ AZURE_SPEECH_KEY or AZURE_SERVICE_REGION not found. Using EdgeTTS."
    else:
        return "ℹ️ Using EdgeTTS (no timing sync)"


# TTS tab
def tts_tab():
    trigger = get_filter_trigger()
    with gr.Column():
        with gr.Row():
            model_file = gr.Dropdown(
                label=i18n("Voice Model"),
                info=i18n("Select the voice model to use for the conversion."),
                choices=sorted(get_files("model"), key=extract_model_and_epoch),
                interactive=True,
                value=default_weight,
                allow_custom_value=True,
            )
            filter_box_tts = gr.Textbox(
                label=i18n("Filter"),
                info=i18n("Path must contain:"),
                placeholder=i18n("Type to filter..."),
                interactive=True,
                scale=0.1,
                visible=load_config_filter(),
                elem_id="filter_box_tts",
            )
            index_file = gr.Dropdown(
                label=i18n("Index File"),
                info=i18n("Select the index file to use for the conversion."),
                choices=sorted(get_files("index")),
                value=match_index(default_weight),
                interactive=True,
                allow_custom_value=True,
            )
            filter_box_tts.blur(
                fn=filter_dropdowns,
                inputs=[filter_box_tts],
                outputs=[model_file, index_file],
            )
            trigger.change(
                fn=update_filter_visibility,
                inputs=[trigger],
                outputs=[filter_box_tts, model_file, index_file],
                show_progress=False,
            )
        with gr.Row():
            unload_button = gr.Button(i18n("Unload Voice"))
            refresh_button = gr.Button(i18n("Refresh"))

            unload_button.click(
                fn=lambda: (
                    {"value": "", "__type__": "update"},
                    {"value": "", "__type__": "update"},
                ),
                inputs=[],
                outputs=[model_file, index_file],
            )

            model_file.select(
                fn=lambda model_file_value: match_index(model_file_value),
                inputs=[model_file],
                outputs=[index_file],
            )

    gr.Markdown(
        i18n(
            f"Applio is a Speech-to-Speech conversion software, utilizing EdgeTTS as middleware for running the Text-to-Speech (TTS) component. Read more about it [here!](https://docs.applio.org/applio/getting-started/tts)"
        )
    )
    tts_voice = gr.Dropdown(
        label=i18n("TTS Voices"),
        info=i18n("Select the TTS voice to use for the conversion."),
        choices=short_names,
        interactive=True,
        value=random.choice(short_names),
    )

    tts_rate = gr.Slider(
        minimum=-100,
        maximum=100,
        step=1,
        label=i18n("TTS Speed"),
        info=i18n("Increase or decrease TTS speed."),
        value=0,
        interactive=True,
    )

    active_tab = gr.State(value=0)

    with gr.Tabs() as tabs:
        with gr.Tab(label=i18n("Text to Speech"), id=0):
            tts_text = gr.Textbox(
                label=i18n("Text to Synthesize"),
                info=i18n("Enter the text to synthesize."),
                placeholder=i18n("Enter text to synthesize"),
                lines=3,
            )
        with gr.Tab(label=i18n("File to Speech"), id=1):
            txt_file = gr.File(
                label=i18n("Upload a .txt file"),
                type="filepath",
            )
            input_tts_path = gr.Textbox(
                label=i18n("Input path for text file"),
                placeholder=i18n(
                    "The path to the text file that contains content for text to speech."
                ),
                value="",
                interactive=True,
            )
        with gr.Tab(label=i18n("SRT to Speech"), id=2):
            srt_file = gr.File(
                label=i18n("Upload SRT File"),
                type="filepath",
                file_types=[".srt"],
            )
            srt_file_path = gr.Textbox(
                label=i18n("SRT File Path"),
                placeholder=i18n("Path to the SRT subtitle file"),
                value="",
                interactive=True,
            )
            use_azure_api = gr.Checkbox(
                label=i18n("Use Azure API (Timing Sync)"),
                info=i18n("Enable to sync audio with subtitle timing. Requires AZURE_SPEECH_KEY env var."),
                value=False,
                visible=AZURE_TTS_ENABLED and bool(AZURE_SPEECH_KEY),
            )
            srt_mode_status = gr.Markdown(
                value=i18n("ℹ️ Using EdgeTTS (no timing sync)"),
                visible=AZURE_TTS_ENABLED and bool(AZURE_SPEECH_KEY),
            )
    
    tabs.select(fn=lambda evt: evt.index if evt is not None else 0, outputs=[active_tab])


    with gr.Accordion(i18n("Advanced Settings"), open=False):
        with gr.Column():
            output_tts_path = gr.Textbox(
                label=i18n("Output Path for TTS Audio"),
                placeholder=i18n("Enter output path"),
                value=os.path.join(now_dir, "assets", "audios", "tts_output.wav"),
                interactive=True,
            )
            output_rvc_path = gr.Textbox(
                label=i18n("Output Path for RVC Audio"),
                placeholder=i18n("Enter output path"),
                value=os.path.join(now_dir, "assets", "audios", "tts_rvc_output.wav"),
                interactive=True,
            )
            export_format = gr.Radio(
                label=i18n("Export Format"),
                info=i18n("Select the format to export the audio."),
                choices=["WAV", "MP3", "FLAC", "OGG", "M4A"],
                value="WAV",
                interactive=True,
            )
            
            # Cache settings
            with gr.Row():
                use_cache = gr.Checkbox(
                    label=i18n("Use TTS Cache"),
                    info=i18n("Cache TTS audio segments to speed up repeated conversions."),
                    value=True,
                )
                cache_size_mb = gr.Number(
                    label=i18n("Max Cache Size (MB)"),
                    info=i18n("Maximum cache size before FIFO cleanup. Set via SRT_TTS_CACHE_SIZE_MB env var."),
                    value=512,
                    minimum=100,
                    maximum=10240,
                    precision=0,
                )
            
            # Cache cleanup buttons
            cache_status = gr.Textbox(
                label=i18n("Cache Status"),
                value="",
                interactive=False,
            )
            with gr.Row():
                clear_1h_btn = gr.Button(i18n("Clear 1 Hour Ago"))
                clear_2h_btn = gr.Button(i18n("Clear 2 Hours Ago"))
                clear_4h_btn = gr.Button(i18n("Clear 4 Hours Ago"))
                clear_8h_btn = gr.Button(i18n("Clear 8 Hours Ago"))
                clear_24h_btn = gr.Button(i18n("Clear 24 Hours Ago"))
                clear_all_btn = gr.Button(i18n("Clear All Cache"), variant="stop")
            
            def do_clear_cache(hours=None):
                result = clear_all_caches(hours)
                api_stats = get_cache_stats(CACHE_DIR)
                output_stats = get_cache_stats(OUTPUT_CACHE_DIR)
                if hours:
                    msg = i18n("Cleared cache older than {} hours").format(hours)
                else:
                    msg = i18n("Cleared all cache")
                msg += f": API({result['api_cache_cleared']}), Output({result['output_cache_cleared']})"
                msg += f"\n{i18n('Current')}: API={api_stats['size_mb']:.1f}MB ({api_stats['file_count']} {i18n('files')}), Output={output_stats['size_mb']:.1f}MB ({output_stats['file_count']} {i18n('files')})"
                return msg
            
            clear_1h_btn.click(fn=lambda: do_clear_cache(1), outputs=[cache_status])
            clear_2h_btn.click(fn=lambda: do_clear_cache(2), outputs=[cache_status])
            clear_4h_btn.click(fn=lambda: do_clear_cache(4), outputs=[cache_status])
            clear_8h_btn.click(fn=lambda: do_clear_cache(8), outputs=[cache_status])
            clear_24h_btn.click(fn=lambda: do_clear_cache(24), outputs=[cache_status])
            clear_all_btn.click(fn=lambda: do_clear_cache(None), outputs=[cache_status])
            
            sid = gr.Dropdown(
                label=i18n("Speaker ID"),
                info=i18n("Select the speaker ID to use for the conversion."),
                choices=get_speakers_id(model_file.value),
                value=0,
                interactive=True,
            )
            split_audio = gr.Checkbox(
                label=i18n("Split Audio"),
                info=i18n(
                    "Split the audio into chunks for inference to obtain better results in some cases."
                ),
                visible=True,
                value=False,
                interactive=True,
            )
            autotune = gr.Checkbox(
                label=i18n("Autotune"),
                info=i18n(
                    "Apply a soft autotune to your inferences, recommended for singing conversions."
                ),
                visible=True,
                value=False,
                interactive=True,
            )
            autotune_strength = gr.Slider(
                minimum=0,
                maximum=1,
                label=i18n("Autotune Strength"),
                info=i18n(
                    "Set the autotune strength - the more you increase it the more it will snap to the chromatic grid."
                ),
                visible=False,
                value=1,
                interactive=True,
            )
            proposed_pitch = gr.Checkbox(
                label=i18n("Proposed Pitch"),
                info=i18n(
                    "Adjust the input audio pitch to match the voice model range."
                ),
                visible=True,
                value=False,
                interactive=True,
            )
            proposed_pitch_threshold = gr.Slider(
                minimum=50.0,
                maximum=1200.0,
                label=i18n("Proposed Pitch Threshold"),
                info=i18n(
                    "Male voice models typically use 155.0 and female voice models typically use 255.0."
                ),
                visible=False,
                value=155.0,
                interactive=True,
            )
            clean_audio = gr.Checkbox(
                label=i18n("Clean Audio"),
                info=i18n(
                    "Clean your audio output using noise detection algorithms, recommended for speaking audios."
                ),
                visible=True,
                value=False,
                interactive=True,
            )
            clean_strength = gr.Slider(
                minimum=0,
                maximum=1,
                label=i18n("Clean Strength"),
                info=i18n(
                    "Set the clean-up level to the audio you want, the more you increase it the more it will clean up, but it is possible that the audio will be more compressed."
                ),
                visible=True,
                value=0.5,
                interactive=True,
            )
            pitch = gr.Slider(
                minimum=-24,
                maximum=24,
                step=1,
                label=i18n("Pitch"),
                info=i18n(
                    "Set the pitch of the audio, the higher the value, the higher the pitch."
                ),
                value=0,
                interactive=True,
            )
            index_rate = gr.Slider(
                minimum=0,
                maximum=1,
                label=i18n("Search Feature Ratio"),
                info=i18n(
                    "Influence exerted by the index file; a higher value corresponds to greater influence. However, opting for lower values can help mitigate artifacts present in the audio."
                ),
                value=0.75,
                interactive=True,
            )
            rms_mix_rate = gr.Slider(
                minimum=0,
                maximum=1,
                label=i18n("Volume Envelope"),
                info=i18n(
                    "Substitute or blend with the volume envelope of the output. The closer the ratio is to 1, the more the output envelope is employed."
                ),
                value=1,
                interactive=True,
            )
            protect = gr.Slider(
                minimum=0,
                maximum=0.5,
                label=i18n("Protect Voiceless Consonants"),
                info=i18n(
                    "Safeguard distinct consonants and breathing sounds to prevent electro-acoustic tearing and other artifacts. Pulling the parameter to its maximum value of 0.5 offers comprehensive protection. However, reducing this value might decrease the extent of protection while potentially mitigating the indexing effect."
                ),
                value=0.5,
                interactive=True,
            )
            f0_method = gr.Radio(
                label=i18n("Pitch extraction algorithm"),
                info=i18n(
                    "Pitch extraction algorithm to use for the audio conversion. The default algorithm is rmvpe, which is recommended for most cases."
                ),
                choices=[
                    "crepe",
                    "crepe-tiny",
                    "rmvpe",
                    "fcpe",
                ],
                value="rmvpe",
                interactive=True,
            )
            embedder_model = gr.Radio(
                label=i18n("Embedder Model"),
                info=i18n("Model used for learning speaker embedding."),
                choices=[
                    "contentvec",
                    "spin",
                    "spin-v2",
                    "chinese-hubert-base",
                    "japanese-hubert-base",
                    "korean-hubert-base",
                    "custom",
                ],
                value="contentvec",
                interactive=True,
            )
            with gr.Column(visible=False) as embedder_custom:
                with gr.Accordion(i18n("Custom Embedder"), open=True):
                    with gr.Row():
                        embedder_model_custom = gr.Dropdown(
                            label=i18n("Select Custom Embedder"),
                            choices=refresh_embedders_folders(),
                            interactive=True,
                            allow_custom_value=True,
                        )
                        refresh_embedders_button = gr.Button(i18n("Refresh embedders"))
                    folder_name_input = gr.Textbox(
                        label=i18n("Folder Name"), interactive=True
                    )
                    with gr.Row():
                        bin_file_upload = gr.File(
                            label=i18n("Upload .bin"),
                            type="filepath",
                            interactive=True,
                        )
                        config_file_upload = gr.File(
                            label=i18n("Upload .json"),
                            type="filepath",
                            interactive=True,
                        )
                    move_files_button = gr.Button(
                        i18n("Move files to custom embedder folder")
                    )
            f0_file = gr.File(
                label=i18n(
                    "The f0 curve represents the variations in the base frequency of a voice over time, showing how pitch rises and falls."
                ),
                visible=True,
            )

    def enforce_terms(terms_accepted, *args):
        if not terms_accepted:
            message = "You must agree to the Terms of Use to proceed."
            gr.Info(message)
            return message, None
        return run_tts_script(*args)

    terms_checkbox = gr.Checkbox(
        label=i18n("I agree to the terms of use"),
        info=i18n(
            "Please ensure compliance with the terms and conditions detailed in [this document](https://github.com/IAHispano/Applio/blob/main/TERMS_OF_USE.md) before proceeding with your inference."
        ),
        value=False,
        interactive=True,
    )
    convert_button = gr.Button(i18n("Convert"))

    with gr.Row():
        vc_output1 = gr.Textbox(
            label=i18n("Output Information"),
            info=i18n("The output information will be displayed here."),
        )
        vc_output2 = gr.Audio(label=i18n("Export Audio"))

    def toggle_visible(checkbox):
        return {"visible": checkbox, "__type__": "update"}

    def toggle_visible_embedder_custom(embedder_model):
        if embedder_model == "custom":
            return {"visible": True, "__type__": "update"}
        return {"visible": False, "__type__": "update"}

    autotune.change(
        fn=toggle_visible,
        inputs=[autotune],
        outputs=[autotune_strength],
    )
    proposed_pitch.change(
        fn=toggle_visible,
        inputs=[proposed_pitch],
        outputs=[proposed_pitch_threshold],
    )
    clean_audio.change(
        fn=toggle_visible,
        inputs=[clean_audio],
        outputs=[clean_strength],
    )
    refresh_button.click(
        fn=change_choices,
        inputs=[model_file],
        outputs=[model_file, index_file, sid, sid],
    ).then(
        fn=filter_dropdowns,
        inputs=[filter_box_tts],
        outputs=[model_file, index_file],
    )
    txt_file.upload(
        fn=process_input,
        inputs=[txt_file],
        outputs=[input_tts_path, txt_file],
    )
    embedder_model.change(
        fn=toggle_visible_embedder_custom,
        inputs=[embedder_model],
        outputs=[embedder_custom],
    )
    move_files_button.click(
        fn=create_folder_and_move_files,
        inputs=[folder_name_input, bin_file_upload, config_file_upload],
        outputs=[],
    )
    refresh_embedders_button.click(
        fn=lambda: gr.update(choices=refresh_embedders_folders()),
        inputs=[],
        outputs=[embedder_model_custom],
    )
    # Combined conversion logic
    def unified_convert(
        terms_accepted,
        active_tab_index,
        input_tts_path,
        tts_text,
        srt_file_path,
        tts_voice,
        tts_rate,
        use_azure_api,
        pitch,
        index_rate,
        rms_mix_rate,
        protect,
        f0_method,
        output_tts_path,
        output_rvc_path,
        model_file,
        index_file,
        split_audio,
        autotune,
        autotune_strength,
        proposed_pitch,
        proposed_pitch_threshold,
        clean_audio,
        clean_strength,
        export_format,
        embedder_model,
        embedder_model_custom,
        sid,
        use_cache,
        cache_size_mb,
    ):
        if not terms_accepted:
            message = "You must agree to the Terms of Use to proceed."
            gr.Info(message)
            return message, None

        # Debug: print which mode is detected
        print(f"[TTS] active_tab_index={active_tab_index}, srt_file_path={srt_file_path}")

        # Determine which mode to use based on the active tab index OR srt_file_path
        # Use SRT mode if active_tab is 2 OR if srt_file_path has a value
        if active_tab_index == 2 or (srt_file_path and srt_file_path.strip()):
            print(f"[TTS] Using SRT to Speech mode")
            return run_srt_tts_script(
                srt_file_path,
                tts_voice,
                tts_rate,
                use_azure_api,
                pitch,
                index_rate,
                rms_mix_rate,
                protect,
                f0_method,
                output_tts_path,
                output_rvc_path,
                model_file,
                index_file,
                split_audio,
                autotune,
                autotune_strength,
                proposed_pitch,
                proposed_pitch_threshold,
                clean_audio,
                clean_strength,
                export_format,
                embedder_model,
                embedder_model_custom,
                sid,
                use_cache,
                int(cache_size_mb),
            )
        else:
            # For index 0 (Text) and 1 (File)
            # Adjust input_tts_path based on text synthesis if needed
            return run_tts_script(
                input_tts_path,
                tts_text,
                tts_voice,
                tts_rate,
                pitch,
                index_rate,
                rms_mix_rate,
                protect,
                f0_method,
                output_tts_path,
                output_rvc_path,
                model_file,
                index_file,
                split_audio,
                autotune,
                autotune_strength,
                proposed_pitch,
                proposed_pitch_threshold,
                clean_audio,
                clean_strength,
                export_format,
                embedder_model,
                embedder_model_custom,
                sid,
            )

    convert_button.click(
        fn=unified_convert,
        inputs=[
            terms_checkbox,
            active_tab,
            input_tts_path,
            tts_text,
            srt_file_path,
            tts_voice,
            tts_rate,
            use_azure_api,
            pitch,
            index_rate,
            rms_mix_rate,
            protect,
            f0_method,
            output_tts_path,
            output_rvc_path,
            model_file,
            index_file,
            split_audio,
            autotune,
            autotune_strength,
            proposed_pitch,
            proposed_pitch_threshold,
            clean_audio,
            clean_strength,
            export_format,
            embedder_model,
            embedder_model_custom,
            sid,
            use_cache,
            cache_size_mb,
        ],
        outputs=[vc_output1, vc_output2],
    )

    # SRT to Speech event handlers
    srt_file.upload(
        fn=process_srt_input,
        inputs=[srt_file],
        outputs=[srt_file_path, srt_file],
    )

    use_azure_api.change(
        fn=check_azure_api_status,
        inputs=[use_azure_api],
        outputs=[srt_mode_status],
    )
