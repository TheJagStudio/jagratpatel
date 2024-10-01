import os
import stable_whisper
import requests
import random
from moviepy.editor import ImageSequenceClip, AudioFileClip
from PIL import Image, ImageDraw, ImageFont
from pydub.utils import mediainfo
import math
import tempfile

audioLength = get_audio_duration(audioPath)

def convert_to_seconds(time_str):
    hours, minutes, seconds = int(time_str.split(':')[0]), int(time_str.split(':')[1]), time_str.split(':')[2]
    seconds, milliseconds = int(seconds.split(',')[0]), int(seconds.split(',')[1])
    total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
    return total_seconds


def interpolate_subtitles(subtitles,audioPath):
    audioLength = get_audio_duration(audioPath)
    subtitlesNew = []
    for index, subtitle in enumerate(subtitles):
        tempData = {}
        if index == 0 and subtitle['start_time'] != 0:
            tempData['start'] = 0
            tempData['end'] = subtitles[index]['start_time']
            tempData['prompt'] = ""
            tempData['duration'] = tempData['end_time'] - tempData['start_time']
            subtitlesNew.append(tempData)
            subtitlesNew.append(subtitle)
        elif index == len(subtitles) - 1 and subtitle['end_time'] != audioLength:
            tempData['start'] = subtitles[index]['end_time']
            tempData['end'] = audioLength
            tempData['prompt'] = ""
            tempData['duration'] = tempData['end_time'] - tempData['start_time']
            subtitlesNew.append(subtitle)
            subtitlesNew.append(tempData)

        else:
            tempData['start'] = subtitles[index]['end_time']
            tempData['end'] = subtitles[index + 1]['start_time']
            tempData['prompt'] = ""
            tempData['duration'] = tempData['end_time'] - tempData['start_time']
            subtitlesNew.append(subtitle)
            subtitlesNew.append(tempData)
    return subtitlesNew

def read_srt_file(file_path):
    subtitles = []
    with open(file_path, 'r') as file:
        lines = file.readlines()
        subtitle = {}
        for line in lines:
            line = line.strip()
            if line.isdigit():
                subtitle['index'] = int(line)
            elif '-->' in line:
                start, end = line.split('-->')
                subtitle['start_time'] = convert_to_seconds(start.strip())
                subtitle['end_time'] = convert_to_seconds(end.strip())
            elif line == '':
                subtitles.append(subtitle)
                subtitle = {}
            else:
                subtitle.setdefault('text', []).append(line)
    return subtitles


def get_audio_duration(file_path):
    info = mediainfo(file_path)
    return math.ceil(float(info['duration']) * 100) / 100


def generate_image(prompt, style, width, height):
    url = f"https://image.pollinations.ai/prompt/{prompt}?height={height}&width={width}&nologo=true&model=flux-{style}&seed={random.randint(0, 1000000)}"
    response = requests.get(url)
    response.raise_for_status()
    return response.content


def process_srt(srt_path, audio_path):
    subtitles = read_srt_file(srt_path)
    subtitlesNew = interpolate_subtitles(subtitles,audio_path)
    result= []
    for subtitle in subtitles:
        print(f"Start Time: {subtitle['start_time']}")
        print(f"End Time: {subtitle['end_time']}")
        print(f"Text: {' '.join(subtitle['text'])}")
        print()
        duration = subtitle['end_time'] - subtitle['start_time']
        for index,text in enumerate(subtitle['text']):
            tempData = {
                "prompt": ' '.join(subtitle['text']),
                "start": subtitle['start_time'] + (index * duration / len(subtitle['text'])) if index > 0 else subtitle['start_time'],
                "end": subtitle['end_time'] - ((len(subtitle['text']) - index - 1) * duration / len(subtitle['text'])) if index < len(subtitle['text']) - 1 else subtitle['end_time'],
                "duration": duration / len(subtitle['text'])
            }
            result.append(tempData)
    return result


def create_video(audio_path, result, style, output_path):
    audio_length = get_audio_duration(audio_path)
    image_files = []

    with tempfile.TemporaryDirectory() as temp_dir:
        for i, segment in enumerate(result):
            prompt = segment.text
            segment_duration = segment["end"] - segment["start"] if i < len(result) - 1 else audio_length - segment["start"]
            images_count = max(1, math.floor(segment_duration / 4))

            for j in range(images_count):
                try:
                    image_content = generate_image(prompt, style, 1920, 1080)
                    img_path = os.path.join(temp_dir, f"{segment['start']:.2f}_{j}.png")
                    with open(img_path, "wb") as f:
                        f.write(image_content)
                    image_files.append({
                        "path": img_path,
                        "duration": segment_duration / images_count,
                        "start": segment["start"],
                        "end": segment["end"],
                        "lyric": prompt
                    })
                except requests.RequestException as e:
                    print(f"Failed to generate image for prompt: {prompt}. Error: {e}")

        # Add lyrics to images
        font = ImageFont.truetype('arial.ttf', 30)  # Make sure 'arial.ttf' is available or replace with an available font
        for image_file in image_files:
            add_lyrics_to_image(image_file, font)

        # Create video
        clip = ImageSequenceClip([img["path"] for img in image_files], durations=[img["duration"] for img in image_files])
        audio = AudioFileClip(audio_path)
        final_clip = clip.set_audio(audio)
        final_clip.write_videofile(output_path, fps=24, audio=True)


def add_lyrics_to_image(image_file, font):
    with Image.open(image_file["path"]) as img:
        draw = ImageDraw.Draw(img)
        add_text_with_background(draw, img.size, image_file["lyric"], font)
        img.save(image_file["path"])


def add_text_with_background(draw, image_size, text, font):
    text_color = (255, 255, 255)  # White text
    background_color = (0, 0, 0, 128)  # Semi-transparent black background
    padding = 10

    # Calculate text size and position
    text_bbox = font.getbbox(text)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    text_position = ((image_size[0] - text_width) // 2, image_size[1] - text_height - 50)

    # Draw background
    background_bbox = (
        text_position[0] - padding,
        text_position[1] - padding,
        text_position[0] + text_width + padding,
        text_position[1] + text_height + padding
    )
    draw.rectangle(background_bbox, fill=background_color)

    # Draw text
    draw.text(text_position, text, font=font, fill=text_color)


if __name__ == "__main__":
    audio_path = "C:/Users/Jagrat Patel/Downloads/audio-wcLG3Vf1qxNmlYaqPy4wg.mp3"
    srt_path = "C:/Users/Jagrat Patel/Downloads/audio-wcLG3Vf1qxNmlYaqPy4wg.srt"
    output_path = "output.mp4"
    style = "realism"

    if not audio_path or not output_path:
        raise ValueError("AUDIO_PATH and OUTPUT_PATH must be set in the .env file")

    result = process_srt(srt_path, audio_path)
    create_video(audio_path, result, style, output_path)
