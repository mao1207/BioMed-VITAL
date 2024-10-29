import argparse
import base64
import json
import os

import openai
from openai import AzureOpenAI

parser = argparse.ArgumentParser(description='ChatGPT-based QA evaluation.')
parser.add_argument('--api_version', type=str, default="")
parser.add_argument('--azure_endpoint', type=str, default="")
parser.add_argument('--api_key', type=str, default="")
args = parser.parse_args()

client = AzureOpenAI(api_version=args.api_version,
azure_endpoint=args.azure_endpoint,
api_key=args.api_key)

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def call_azure_openai_to_generate_answer(conversation):
    while True:
        try:
            response = client.chat.completions.create(model="vision",
                                                        messages=conversation,
                                                        max_tokens=4096)
            # If the request is successful, break the loop
            break
        except openai.RateLimitError as e:
            print("Rate limit exceeded. Waiting for a while to retry...")
            time.sleep(30)
        except openai.BadRequestError as e:
            print(f"An error occurred while processing the image: {e}")
            response = "none"
            break

    return response

# Read files
def read_jsonl_file(file_path):
    with open(file_path, 'r') as json_file:
        data_list = [json.loads(line) for line in json_file]
    return data_list

# Write back files
def write_jsonl_file(data_list, file_path):
    with open(file_path, 'w') as json_file:
        for entry in data_list:
            json_file.write(json.dumps(entry) + '\n')

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

input_file_path = "/local/scratch/hcui25/Project/xin/LLaVA-Med/data/eval/llava_med_eval_qa50_qa.jsonl"
output_file_path = "/local/scratch/hcui25/Project/xin/LLaVA-Med/data/eval/llava_med_eval_qa50_qa_updated.jsonl"
data_list = read_jsonl_file(input_file_path)

# Iterate through the data list, update the answers, and collect a new data list
updated_data_list = []
for ex in data_list:
    
    messages = [
    {"role": "system", "content": "You are an AI assistant with expertise in biomedical subjects. You will receive an image from a biomedical research paper along with additional text (Figure Context) that pertains to the image. When presented with medical-related inquiries, it is imperative that you synthesize the information from both the image and the associated text to formulate your answers. Strive for conciseness and precision in your responses, which should be brief — typically a few sentences — while ensuring they remain helpful, relevant, and accurate, with the necessary level of detail."},
]



    image_path = "/local/scratch/hcui25/Project/xin/LLaVA-Med/data/images/" + ex['image']

    if os.path.exists(image_path):
    
        # Encode images as base64
        base64_image = encode_image(image_path)
        
        # Generate Context
        context = context_gen(ex, use_inline_mentions=True)
        
        # Create dialog
        conversation = {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                {"type": "text", "text": "This is the context in which the image is referenced in the paper: " + context}
            ]
        }
        messages.append(conversation)

        # Generate New Answers with the Azure OpenAI Client
        new_answer = call_azure_openai_to_generate_answer(messages)
        
        # Update the gpt4_answer field
        if new_answer != "none":
            print(new_answer.choices[0].message.content)
            ex['gpt4_answer'] = new_answer.choices[0].message.content
    
    # Add updated entries to the new data list
    updated_data_list.append(ex)

# Write the updated data list back to a new JSONL file
write_jsonl_file(updated_data_list, output_file_path)
