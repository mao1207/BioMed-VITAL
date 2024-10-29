import argparse
import hashlib
import itertools
import os
import sys
import time
from pathlib import Path

import openai
from openai import AzureOpenAI

sys.path.append(str(Path(__file__).resolve().parents[2]))
print(str(Path(__file__).resolve().parents[2]))

import base64
import json

import instruct_few_shot_examples
import instruct_few_shot_examples_2_answers
import instruct_few_shot_examples_add_imgs

parser = argparse.ArgumentParser(description='ChatGPT-based QA evaluation.')
parser.add_argument('--processes_sum', type=int, default=4)
parser.add_argument('--processes_id', type=int, default=0)
parser.add_argument('--img_dir', type=str, default="/local/scratch/hcui25/Project/xin/LLaVA-Med/data/images/")
parser.add_argument('--output_dir', type=str, default="/local/scratch/hcui25/Project/xin/LLaVA-Med/data/instruct/vision_instruction_2_answers.json")
parser.add_argument('--api_version', type=str, default="")
parser.add_argument('--azure_endpoint', type=str, default="")
parser.add_argument('--api_key', type=str, default="")
args = parser.parse_args()

conv_to_str = lambda conv: "\n\n".join([("User: " if x["from"] == "human" else "Assistant: ") + x["value"] for x in conv])

client = AzureOpenAI(api_version=args.api_version,
azure_endpoint=args.azure_endpoint,
api_key=args.api_key)

# Function to encode the image
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def check_image_in_json(json_file, image_id):
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
    {
        "role": "system",
        "content": [
            {
                "type": "text",
                "text": '''You are an AI assistant with expertise in biomedical imagery. You will be presented with an image from a biomedical research paper. Sometimes, additional textual information (Figure Context) related to the image may be provided. Please meticulously extract all possible visual details from the image, and when generating questions and answers, ensure to integrate and consider the provided supplementary textual information. It is crucial to highlight the connections and correlations between the textual content and the visual elements within the picture to capture the full context.

                For every question posed by the User about the image, you are required to craft two separate answers (Answer1 Answer2). Each answer should offer a unique explanation or perspective based on the image's visual content. This dual-answer format is intended to present alternative insights and to help determine which response might be more informative or appropriate.

                Here are the revised guidelines for the dialogue:
                - Do not use specific facts, terms, abbreviations, dates, numbers, or names from the supplementary text to ensure the focus remains on the image itself.
                - Create diverse questions that explore different visual aspects of the image.
                - Provide a minimum of 3-4 rounds (each round includes one question and two answers) of Q&A, with each question followed by two distinct answers.
                - Respond thoughtfully, without overconfidence, and refrain from offering medical advice or diagnoses. Encourage seeking professional medical consultation.
                - Initiate the conversation with a question from the User, not with an answer from the Assistant.
                - Extract and utilize as much critical visual information from the image as possible, complemented by the additional text provided.'''
            }
        ]
    }
]

    for ex in instruct_few_shot_examples_2_answers.fs:
      # Path to your image
      image_path = "/local/scratch/hcui25/Project/xin/LLaVA-Med/llava/instruct/imgs/" + ex['imgs']

      # Getting the base64 string
      base64_image = encode_image(image_path)

      messages += [
        {"role": "user", "content": [
           {"type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
           },
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
      break


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
            time.sleep(20)  # Wait a little while and retry
        except json.JSONDecodeError as e:
            # If JSON decoding fails, the file may be corrupt or in the process of being written. A recovery strategy can be added here.
            attempt += 1
            print(f"JSONDecodeError occurred: {e}. Retrying {attempt}/{max_retries}...")
            time.sleep(20)  # Wait a little while and retry


json_file_path = '/local/scratch/hcui25/Project/xin/LLaVA-Med/data/instruct/cluster_samples.json'
with open(json_file_path) as f:
    domain_dict = json.load(f)
mode = 'gpt-vision'

if mode == 'gpt-vision':
    img_dir = args.img_dir
    output_dir = args.output_dir

    instructions = []
    batch_size = 1  # Set the batch size
    batch_counter = 0  # Initialize the batch counter
    total_count = 0
    flag = True

    processes_sum = args.processes_sum
    processes_id = args.processes_id

    for cycle_idx, content in enumerate(domain_dict):
        
        if content is not None:
            imgs_request = img_dir + content['pair_id'] + ".jpg"
        else:
            imgs_request = "none"


        if os.path.exists(imgs_request):

            text_request = content['fig_caption']
            message = few_shot_messages_gen(imgs_request, text_request, context_gen(content))
            print(message)

            try:
                # if flag:
                #    if content['pair_id'] == "30254804_FIG1":
                #       flag = False
                #       total_count = 50
                #    continue

                if check_image_in_json(output_dir, content['pair_id'] + ".jpg"):
                    continue

                while True:
                    try:
                        response = client.chat.completions.create(model="vision",
                                                                    messages=message,
                                                                    max_tokens=4096)
                        # If the request is successful, break the loop
                        break
                    except openai.RateLimitError as e:
                        print("Rate limit exceeded. Waiting for a while to retry...")
                        time.sleep(30)


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
                    "domain": content['domain'],
                    "conversations": conversations
                })

                batch_counter += 1
                if batch_counter >= batch_size:
                    # Write file and reset counter
                    append_to_json_file(output_dir, instructions)
                    instructions = []  # Clear the list of commands for the current batch
                    batch_counter = 0

            except openai.BadRequestError as e:
                print(f"An error occurred while processing the image: {e}")
                continue
        

    print("end")
    # Processing of remaining instructions
    if instructions:
        append_to_json_file(output_dir, instructions)
