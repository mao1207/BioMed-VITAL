import argparse
import asyncio
import base64
import hashlib
import itertools
import json
import os
import random
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

import doctor_few_shot_examples
from openai import AsyncAzureOpenAI, AsyncOpenAI, AzureOpenAI

parser = argparse.ArgumentParser()

# used for distributed data generation
parser.add_argument('--processes_sum', type=int, default=4)
parser.add_argument('--processes_id', type=int, default=0)

parser.add_argument('--img_dir', type=str, default="")
parser.add_argument('--output_dir', type=str, default="")
parser.add_argument('--api_version', type=str, default="")
parser.add_argument('--azure_endpoint', type=str, default="")
parser.add_argument('--api_key', type=str, default="")
args = parser.parse_args()

conv_to_str = lambda conv: "\n\n".join([("User: " if x["from"] == "human" else "Assistant: ") + x["value"] for x in conv])

# Function to encode the image
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def check_image_in_json(json_file, image_id):
    if os.path.exists(json_file) == False:
        return False

    with open(json_file, 'r', encoding='utf-8') as file:
        data = json.load(file)

    for entry in data:
        if entry.get('image') == image_id:
            print("Duplicate images exist")
            return True
    return False

def context_gen(sample, use_inline_mentions=True):
  ctx = []
  if use_inline_mentions and sample["in_text_mention"]:
    for sent in sample["in_text_mention"]:
      if isinstance(sent, dict):
        sent = sent["tokens"]
      ctx.append(sent)
  ret = f"Figure Caption:\n{sample['fig_label']}: {sample['fig_caption']}"
  if len(ctx):
    ret += "\n\nFigure Context:\n\t- {ctx}".format(ctx="\n\t- ".join(ctx))
  return ret

def few_shot_messages_gen(image_path_request, request_text, inline_mentions, use_inline_mentions = True):
    
    messages = [
        {"role": "system", 
        "content": [
            {"type": "text", 
            "text": """You are an AI assistant specialized in biomedical topics.
            You are provided with a figure image from a biomedical research paper. In some cases, you may have additional text (Figure Context) that mentions the image. Please meticulously extract all possible visual details from the image, and when generating questions and answers, ensure to integrate and consider the provided supplementary textual information. It is crucial to highlight the connections and correlations between the textual content and the visual elements within the picture to capture the full context.

            Your task is to facilitate a dialogue where a person (User) seeks information about the image, and you (Assistant) provide insightful responses. During this interaction, the conversation should evolve as if both the User and Assistant are observing the image together. It is essential to thoroughly consider and reference the accompanying textual information (Figure Caption and Figure Context) and visual information to ensure a rich and informative exchange that highlights the significance of the visual details present.

            Below are requirements for generating the questions and answers in the conversation:
            - Focus on visual aspects of the image that can be inferred without the text information, and extract as much key detailed information from the image as possible..
            - Ensure that the questions are diverse and cover a range of visual aspects of the image, and each question should has its corresponding answer. Questions can include judgments on imaging modalities, organs, locations, potential diseases, sizes, and the number of elements, as well as more complex reasoning. Question types can include yes/no evaluations and open-ended discussions.
            - The conversation should encompass a minimum of 4-5 exchanges of questions and answers. You may adjust the number of rounds based on the provided image and text. For content with substantial information, employing additional questions and answers may be more appropriate to ensure thorough discussion and understanding.
            - When the provided textual information is relevant to the question, try to answer using the expertise and specialized terminology contained within the text, rather than with vague, non-specialized descriptions.
            - Answer responsibly, avoiding overconfidence, avoiding vague answers.
            - You need to start by generating the User's questions first, not assistant's answer.
            - The instruction following datasets you have generated are intended for training another large medical model. Therefore, please ensure that the question-and-answer pairs you create are highly beneficial for training other Vision Language models."""}]
        }
    ]
           
    # Grouping by modality
    modality_examples = defaultdict(list)
 
    for ex in doctor_few_shot_examples.fs:
        for modality, is_present in ex['domain'].items():
            if is_present:
                modality_examples[modality].append(ex)

  
    # Randomly selected one/two example for each modality
    sampled_few_shot_examples = {modality: random.sample(examples, 1) for modality, examples in modality_examples.items()}

    for examples in sampled_few_shot_examples.values():
        for ex in examples:

            image_path = args.img_dir + ex['imgs']

            # Getting the base64 string
            base64_image = encode_image(image_path)

            messages += [
                {"role": "user", "content": [
                {"type": "text",
                    "text": "This is some text that describes the image, you can refer to see it as an expansion of the image:" + ex['fig_caption']},
                {"type": "text",
                    "text": "This is the context in which the image is referenced in the paper:" + context_gen(ex, use_inline_mentions)
                }
                ]},
                {"role": "assistant","content": [
                    {"type": "text",
                    "text": conv_to_str(ex["conversations"])
                    }
                ],
                }
            ]

    base64_image_request = encode_image(image_path_request)
    messages.append(
        {"role": "user",
        "content": [
            {"type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_image_request}"}},
            {"type": "text",
            "text": "This is some text that describes the image, you can refer to see it as an expansion of the image:" + request_text},
            {"type": "text",
            "text": "This is the context in which the image is referenced in the paper:" + inline_mentions},
        ],
        })
            
    return messages

def process_conversation(conversation_list):
    conversations = []
    for text in conversation_list:
        speaker, message = text.split(":", 1)
        speaker = speaker.strip().lower()
        conversations.append({
            "from": "human" if speaker == "user" else "gpt",
            "value": message.strip()
        })
    return conversations

def load_multiple_json_objects(filepath):
    with open(filepath, 'r', encoding='utf-8') as file:
        content = file.read()
    
    json_objects = content.split('\n')

    data = []
    for json_str in json_objects:
        if json_str.strip():
            try:
                data.append(json.loads(json_str))
            except json.JSONDecodeError as e:
                print(f"error{e}")
    return data

def append_to_json_file(file_path, new_data, max_retries=10000):
    attempt = 0
    while True:
        try:
            # If the file exists, read the existing data
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as file:
                    existing_data = json.load(file)
            else:
                existing_data = []

            # Add new data
            existing_data.extend(new_data)

            # Write back updated data
            with open(file_path, 'w', encoding='utf-8') as file:
                json.dump(existing_data, file, ensure_ascii=False, indent=4)
            
            # If successful, exit the loop
            break

        except IOError as e:
            attempt += 1
            print(f"IOError occurred: {e}. Retrying {attempt}/{max_retries}...")
            
            # Wait a little while and retry
            time.sleep(20)
        except json.JSONDecodeError as e:
            # If JSON decoding fails, the file may be corrupt or in the process of being written. A recovery strategy can be added here.
            attempt += 1
            print(f"JSONDecodeError occurred: {e}. Retrying {attempt}/{max_retries}...")
            
            # Wait a little while and retry
            time.sleep(20)


json_file_path = 'llava_med_instruct_fig_captions.json'
with open(json_file_path) as f:
    domain_dict = json.load(f)
mode = 'gpt-vision'

def consistent_hash(key, num_buckets):
    hash_digest = hashlib.sha256(key.encode()).digest()
    return int.from_bytes(hash_digest, byteorder='big') % num_buckets


async def collect(api_version, azure_endpoint, api_key, img_dir, output_dir, processes_sum, processes_id, model_name):

    client = AsyncAzureOpenAI(api_version=api_version,
        azure_endpoint=azure_endpoint,
        api_key=api_key)

    instructions = []
    batch_size = 1  # Set the batch size
    batch_counter = 0  # Initialize the batch counter
    total_count = 0
    flag = True

    step = 0

    for cycle_idx, samples in enumerate(itertools.zip_longest(*domain_dict.values())):
        
        for domain_idx, content in enumerate(samples):

          if content is not None:
            imgs_request = img_dir + content['pair_id'] + ".jpg"

          else:
            imgs_request = "none"

          md5_int = bucket = consistent_hash(imgs_request, 15)
          if md5_int % processes_sum != processes_id:
            continue

          print("processes_id", processes_id)


          if os.path.exists(imgs_request):

            text_request = content['fig_caption']
            message = few_shot_messages_gen(imgs_request, text_request, context_gen(content))

            try:

                img_name = content['pair_id'] + '.jpg'
                if check_image_in_json(output_dir, img_name) or check_image_in_json('/local/scratch/hcui25/Project/xin/LLaVA-Med/data/instruct2/jsons/total2.json', img_name):
                    continue

                flag = 0
                while True:
                    try:
                        print("begin")
                        response = await client.chat.completions.create(model=model_name,
                                                                  messages=message,
                                                                  max_tokens=4096)
                        print("end")
                        # If the request is successful, break the loop
                        break
                    except openai.RateLimitError as e:
                        print("Rate limit exceeded. Waiting for a while to retry...")
                        time.sleep(30)
                    except openai.InternalServerError as e:
                        print("InternalServerError. Waiting for a while to retry...")
                        time.sleep(30)
                        flag = 1

                if flag:
                    continue


                api_output = response.choices[0].message.content
                print(api_output)
                conversation_parts = api_output.strip().split("\n")

                total_count += 1
                print(total_count)

                conversations = []
                for part in conversation_parts:
                    if part.startswith("User:"):
                        speaker = "human"
                    elif part.startswith("Assistant:"):
                        speaker = "gpt"
                    else:
                        continue

                    text = part.split(":", 1)[1].strip()
                    conversations.append({
                        "from": speaker,
                        "value": text
                    })

                instructions.append({
                    "id": total_count,
                    "image": content['pair_id'] + ".jpg",
                    # "image": content['imgs'],
                    "domain": content['domain'],
                    "conversations": conversations
                })

                batch_counter += 1
                if batch_counter >= batch_size:
                    append_to_json_file(output_dir, instructions)
                    instructions = []
                    batch_counter = 0

            except openai.BadRequestError as e:
                print(f"An error occurred while processing the image: {e}")
                continue
        

    # Processing of remaining instructions
    if instructions:
        append_to_json_file(output_dir, instructions)

def thread_function(api_version, azure_endpoint, api_key, img_dir, output_dir, processes_sum, processes_id, model_name):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(collect(api_version, azure_endpoint, api_key, img_dir, output_dir, processes_sum, processes_id, model_name))
    loop.close()

def main():
    img_dir = args.img_dir
    processes_sum = 5

    threads = []

    # You can assign different models to different threads
    for i in range(processes_sum):

        thread = threading.Thread(target=thread_function, args=(args.api_version, args.azure_endpoint, args.api_key, args.img_dir, args.output_dir, processes_sum, i, model_name))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

main()