import openai
import pyaudio
from pydub import AudioSegment
import wave
import io
import keyboard
from boto3 import Session
from botocore.exceptions import BotoCoreError, ClientError
from contextlib import closing
import os
import sys
import subprocess
from config import config

openai.api_key = config.get("openai_api_key")


# Create a client using the credentials and region defined in the config.py file

session = Session()
polly = session.client("polly", region_name=config.get("aws_region"), aws_access_key_id=config.get("aws_access_id"),
                       aws_secret_access_key=config.get("aws_access_key"))


def record_audio():
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100

    audio = pyaudio.PyAudio()

    stream = audio.open(format=FORMAT, channels=CHANNELS,
                        rate=RATE, input=True,
                        frames_per_buffer=CHUNK)

    print("Recording started...")

    frames = []

    while keyboard.is_pressed('-'):
        data = stream.read(CHUNK)
        frames.append(data)

    print("Recording finished.")

    stream.stop_stream()
    stream.close()
    audio.terminate()

    return frames


def get_audio_duration(frames, sample_rate=44100):
    duration = len(frames) / sample_rate
    return duration


def chat_gpt(msg):
    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=msg)
    return completion.choices[0].message["content"]


def play_audio(file_path):
    chunk = 1024

    # Load the MP3 file using pydub
    audio = AudioSegment.from_mp3(file_path)

    # Convert the audio to raw PCM data
    raw_data = audio.raw_data
    sample_width = audio.sample_width
    channels = audio.channels
    frame_rate = audio.frame_rate

    # Initialize PyAudio
    p = pyaudio.PyAudio()

    # Open the audio stream
    stream = p.open(format=p.get_format_from_width(sample_width),
                    channels=channels,
                    rate=frame_rate,
                    output=True)

    # Play the audio
    stream.write(raw_data)

    # Cleanup
    stream.stop_stream()
    stream.close()
    p.terminate()


def polly_req(txt):
    try:
        # Request speech synthesis
        response = polly.synthesize_speech(Text=txt, OutputFormat="mp3",
                                           VoiceId="Stephen", Engine="neural")
    except (BotoCoreError, ClientError) as error:
        # The service returned an error, exit gracefully
        print(error)
        # sys.exit(-1)
        return "ERROR"

    # Access the audio stream from the response
    if "AudioStream" in response:
        # Note: Closing the stream is important because the service throttles on the
        # number of parallel connections. Here we are using contextlib.closing to
        # ensure the close method of the stream object will be called automatically
        # at the end of the with statement's scope.
        with closing(response["AudioStream"]) as stream:
            output = os.path.join("speech.mp3")

            try:
                # Open a file for writing the output as a binary stream
                with open(output, "wb") as file:
                    file.write(stream.read())
            except IOError as error:
                # Could not write to file, exit gracefully
                print(error)
                # sys.exit(-1)
                return "ERROR"

    else:
        # The response didn't contain audio data, exit gracefully
        print("Could not stream audio")
        # sys.exit(-1)
        return "ERROR"

    # Play the audio using the platform's default player
    if sys.platform == "win32":
        # os.startfile(output)
        print("..")
        play_audio("./speech.mp3")
    else:
        # The following works on macOS and Linux. (Darwin = mac, xdg-open = linux).
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.call([opener, output])


if __name__ == '__main__':
    role = input(
        "Choose role for the AI assistant (english teacher/custom/no role)\n")

    role_en_teacher = "I want you to act as a spoken English teacher and improver. I will speak to you in English and you will reply to me in English to practice my spoken English. I want you to keep your reply neat, limiting the reply to 100 words. I want you to strictly correct my grammar mistakes, typos, and factual errors. I want you to ask me a question in your reply. Now let's start practicing, you could ask me a question first. Remember, I want you to strictly correct my grammar mistakes, typos, and factual errors."
    role_custom = ""

    if (role == "english teacher"):
        messages = [{"role": "system", "content": role_en_teacher}]
    if (role == "custom"):
        custom_role = input("Enter a description for the custom role.\n")
        messages = [{"role": "system", "content": custom_role}]
    if (role == "no role"):
        messages = []

    while True:
        keyboard.wait('-')
        frames = record_audio()
        duration = get_audio_duration(frames)
        print(duration)
        if (duration > 0.001):
            audio_data = b''.join(frames)
            audio_segment = AudioSegment(
                data=audio_data,
                sample_width=pyaudio.get_sample_size(pyaudio.paInt16),
                channels=1,
                frame_rate=44100)

            audio_segment.export("test" + ".mp3", format='mp3')
            audio_file = open(f"./test.mp3", "rb")
            transcript = openai.Audio.transcribe(
                "whisper-1",  audio_file, language="en")
            text: str = transcript.get('text')

            print(f"[User]: {text}")
            messages.append(
                {"role": "user", "content": text})
            res: str = chat_gpt(messages)
            print(f"[ChatBot]: {res}")
            polly_res = polly_req(res)
            if (polly_res == "ERROR"):
                print("[Error]: Something went wrong with Polly TTS.")
            messages.append({"role": "assistant", "content": res})
