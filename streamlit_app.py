import streamlit as st
import PyPDF2
import openai
import os
from gtts import gTTS
from playsound import playsound
import wave
from tempfile import NamedTemporaryFile
import pyaudio
import queue
import time
from azure.cognitiveservices.speech import AudioDataStream, SpeechConfig, SpeechRecognizer
from azure.cognitiveservices.speech.audio import AudioOutputConfig
from azure.cognitiveservices.speech import ResultReason, CancellationReason
from streamlit_chat import message

class MicrophoneStream(object):
    """Opens a recording stream as a generator yielding the audio chunks."""

    def __init__(self, rate, chunk):
        self._rate = rate
        self._chunk = chunk

        # Create a thread-safe buffer of audio data
        self._buff = queue.Queue()
        self.closed = True

    def __enter__(self):
        self._audio_interface = pyaudio.PyAudio()
        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            # The API currently only supports 1-channel (mono) audio
            # https://goo.gl/z757pE
            channels=1,
            rate=self._rate,
            input=True,
            frames_per_buffer=self._chunk,
            # Run the audio stream asynchronously to fill the buffer object.
            # This is necessary so that the input device's buffer doesn't
            # overflow while the calling thread makes network requests, etc.
            stream_callback=self._fill_buffer,
        )

        self.closed = False

        return self

    def __exit__(self, type, value, traceback):
        self._audio_stream.stop_stream()
        self._audio_stream.close()
        self.closed = True
        # Signal the generator to terminate so that the client's
        # streaming_recognize method will not block the process termination.
        self._buff.put(None)
        self._audio_interface.terminate()

    def _fill_buffer(self, in_data, frame_count, time_info, status_flags):
        """Continuously collect data from the audio stream, into the buffer."""
        self._buff.put(in_data)
        return None, pyaudio.paContinue

    def generator(self):
        while not self.closed:
            # Use a blocking get() to ensure there's at least one chunk of
            # data, and stop iteration if the chunk is None, indicating the
            # end of the audio stream.
            chunk = self._buff.get()
            if chunk is None:
                return
            data = [chunk]

            # Now consume whatever other data's still buffered.
            while True:
                try:
                    chunk = self._buff.get(block=False)
                    if chunk is None:
                        return
                    data.append(chunk)
                except queue.Empty:
                    break

            yield b"".join(data)

def listen_print_loop(speech_config):
    """Continuously collect data from the audio stream, into the buffer."""
    speech_recognizer = SpeechRecognizer(speech_config=speech_config)
    done = False
    while not done:
        result = speech_recognizer.recognize_once_async().get()
        if result.reason == ResultReason.RecognizedSpeech:
            print(result.text)
        elif result.reason == ResultReason.NoMatch:
            print("No speech could be recognized")
        elif result.reason == ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            print(f"Speech Recognition canceled: {cancellation_details.reason}")
            if cancellation_details.reason == CancellationReason.Error:
                print(f"Error details: {cancellation_details.error_details}")
        done = True

def play_audio(msg):
    tts = gTTS(text=msg, lang='en')
    
    # create temporary file with specified name
    f = NamedTemporaryFile(suffix=".mp3", delete=False)
    tts.write_to_fp(f)
    f.close()
    audio_file_path = os.path.abspath(f.name)

    # play audio file
    playsound(audio_file_path)

class chatbot:
    def __init__(self):
        openai.api_key = os.environ.get("OPENAI_API_KEY")
        self.messages = [
            {"role": "system", "content": "You are a good interviewer"},
        ]

    def conversation(self, your_text):
        self.messages.append({"role": "user", "content": your_text})
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=self.messages
        )
        self.messages.append({"role": "assistant", "content": response["choices"][0]["message"].content})
        return response

st.markdown("# <center>InterviewGPT</center>", unsafe_allow_html=True)
st.markdown("### <center>你的私人英语 AI 面试官</center>", unsafe_allow_html=True)

if 'generated' not in st.session_state:
    st.session_state['generated'] = []
    bot = chatbot()
    st.session_state['bot'] = bot

if 'past' not in st.session_state:
    st.session_state['past'] = []

# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms

# 上传PDF文件
file = st.file_uploader("上传简历(仅限于PDF)", type="pdf")
a = st.button('点击说话', key='wide_button', use_container_width = True)

if file is not None:
    if st.session_state['generated'] == []:
        with st.spinner('......'):
            time.sleep(7)
            
        bot = st.session_state['bot']
        
        # 读取PDF文件内容
        pdf_reader = PyPDF2.PdfReader(file)
        content = ''
        for page in range(len(pdf_reader.pages)):
            content += pdf_reader.pages[page].extract_text()
        print(content)
        
        input = "Now I am an interviewee, I need you to act as my interviewer and have a mock English interview with me, you can only ask me 1 question at 1 time, here is my resume"+ content
        response = bot.conversation(your_text = input)
        msg = response["choices"][0]["message"].content
        print("gpt:"+ msg)
        st.session_state.generated.append(msg)
        #list_questions.append(msg)
        #print(st.session_state)
        message(msg)
        play_audio(msg)
        file.close()

if a:

    speech_key = os.environ.get("SPEECH_KEY")
    service_region = os.environ.get("SERVICE_REGION")
    language = "en-US"
    speech_config = SpeechConfig(subscription=speech_key, region=service_region)
    speech_config.speech_recognition_language = language
    audio_config = AudioOutputConfig(use_default_speaker=True)    
    stream = MicrophoneStream(RATE, CHUNK)
    audio_generator = stream.generator()
    speech_recognizer = SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    
    print("Speak into your microphone.")
    result = speech_recognizer.recognize_once_async().get()
    print(result.text)
    
    input = result.text
    st.session_state.past.append(input)
    print(st.session_state)
    #list_answers.append(input)

    bot = st.session_state['bot']
    response = bot.conversation(your_text = input)
    msg = response["choices"][0]["message"].content
    print(msg)
    st.session_state.generated.append(msg)
    print(st.session_state)

    if st.session_state['generated']:
        for i in range(len(st.session_state['generated'])):
            print(i)
            message(st.session_state["generated"][i], key=str(i))
            if i < len(st.session_state['past']):
                message(st.session_state['past'][i], is_user=True, key=str(i) + '_user')
            
    play_audio(msg)
    

