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
import instruct_few_shot_examples_add_imgs

parser = argparse.ArgumentParser(description='ChatGPT-based QA evaluation.')
parser.add_argument('--processes_sum', type=int, default=4)
parser.add_argument('--processes_id', type=int, default=0)
parser.add_argument('--img_dir', type=str, default="/local/scratch/hcui25/Project/xin/LLaVA-Med/data/images/")
parser.add_argument('--output_dir', type=str, default="/local/scratch/hcui25/Project/xin/LLaVA-Med/data/instruct/vision_instruction.json")
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
        {"role": "system", 
        "content": [
            {"type": "text", 
            "text": """You are an AI assistant specialized in biomedical topics.
            You are provided with a figure image from a biomedical research paper. In some cases, you may have additional text (Figure Context) that mentions the image. Please meticulously extract all possible visual details from the image, and when generating questions and answers, ensure to integrate and consider the provided supplementary textual information. It is crucial to highlight the connections and correlations between the textual content and the visual elements within the picture to capture the full context.

            Your task is to facilitate a dialogue where a person (User) seeks information about the image, and you (Assistant) provide insightful responses. During this interaction, the conversation should evolve as if both the User and Assistant are observing the image together. It is essential to thoroughly consider and reference the accompanying textual information (Figure Caption and Figure Context) to ensure a rich and informative exchange that highlights the significance of the visual details present.

            Below are requirements for generating the questions and answers in the conversation:
            - Avoid quoting or referring to specific facts, terms, abbreviations, dates, numbers, or names, as these may reveal the conversation is based on the text information, rather than the image itself. Focus on the visual aspects of the image that can be inferred without the text information.
            - Ensure that questions are diverse and cover a range of visual aspects of the image.
            - The conversation should encompass a minimum of 4-5 exchanges of questions and answers. You may adjust the number of rounds based on the provided image and text. For content with substantial information, employing additional questions and answers may be more appropriate to ensure thorough discussion and understanding.
            - Answer responsibly, avoiding overconfidence, and do not provide medical advice or diagnostic information. Encourage the user to consult a healthcare professional for advice.
            - You need to start by generating the User's questions first, not assistant's answer.
            - Extract as much key detailed information from the image as possible, and I will also provide you with some text to supplement the image."""}]
        }
    ]
    for ex in instruct_few_shot_examples_add_imgs.fs:

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

def few_shot_messages_gen_before(sample, use_inline_mentions = True):
    messages = [
    {"role": "system", "content": """You are an AI assistant specialized in biomedical topics.

  You are provided with a text description (Figure Caption) of a figure image from a biomedical research paper. In some cases, you may have additional text (Figure Context) that mentions the image. Unfortunately, you don't have access to the actual image.

  Your task is to generate a conversation between a person (User) inquiring about the image and you (Assistant) responding to their questions. The conversation should proceed as though both the User and Assistant are viewing the image, while not referring to the text information (Figure Caption and Figure Context). 

  Below are requirements for generating the questions and answers in the conversation:
  - Avoid quoting or referring to specific facts, terms, abbreviations, dates, numbers, or names, as these may reveal the conversation is based on the text information, rather than the image itself. Focus on the visual aspects of the image that can be inferred without the text information.
  - Do not use phrases like "mentioned", "caption", "context" in the conversation. Instead, refer to the information as being "in the image."
  - Ensure that questions are diverse and cover a range of visual aspects of the image.
  - The conversation should include at least 2-3 turns of questions and answers about the visual aspects of the image.
  - Answer responsibly, avoiding overconfidence, and do not provide medical advice or diagnostic information. Encourage the user to consult a healthcare professional for advice.
  """},
    ]
    for ex in instruct_few_shot_examples.fs:
      messages += [
        {"role": "user", "content": context_gen(ex, use_inline_mentions)},
        {"role": "assistant", "content": conv_to_str(ex["conversations"])},
      ]
    messages.append({"role": "user", "content": context_gen(sample, use_inline_mentions=use_inline_mentions)})
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
            time.sleep(20)  # Wait a little while and retry
        except json.JSONDecodeError as e:
            # If JSON decoding fails, the file may be corrupt or in the process of being written. A recovery strategy can be added here.
            attempt += 1
            print(f"JSONDecodeError occurred: {e}. Retrying {attempt}/{max_retries}...")
            time.sleep(20)  # Wait a little while and retry


json_file_path = '/local/scratch/hcui25/Project/xin/LLaVA-Med/data/instruct/llava_med_instruct_fig_captions.json'
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

    for cycle_idx, samples in enumerate(itertools.zip_longest(*domain_dict.values())):
        
        for domain_idx, content in enumerate(samples):
          if content is not None:
            imgs_request = img_dir + content['pair_id'] + ".jpg"
          else:
            imgs_request = "none"

          md5_hash = hashlib.md5(imgs_request.encode()).hexdigest()
          md5_int = int(md5_hash, 16)
          if md5_int % processes_sum != processes_id:
            break


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


if mode == 'gpt3.5':
    instructions = []

    for index, content in enumerate(data):
        if index == 50:
          break
        message = few_shot_messages_gen_before(content)
        print(message)
        response = client.chat.completions.create(model="gpt-3.5-turbo",
        messages=message,
        max_tokens=1000)

        api_output = response.choices[0].message.content

        conversation_parts = api_output.strip().split("\n")


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
              "id": index,
              "image": content['image'],
              "conversations": conversations
          })
        
        print(conversations)

    with open('llava/instruct/text_instruction.json', 'w', encoding='utf-8') as f:
      json.dump(instructions, f, ensure_ascii=False, indent=4)
