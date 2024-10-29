import argparse
import base64
import json
import os
import re
import sys
import time
from collections import defaultdict
from copy import deepcopy
from pprint import pprint

import requests

sys.path.append("llava")
from openai_api import call_async


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


class LLMEvalPromptGenerator:
    instruct_prompt = """Assume that you are a medical expert with extensive experience in your field. Your task is to assess and score a question-and-answer pair from an instruction following dataset designed for fine-tuning a medical large language model (LLM). You should give one score for this Q-A pair. You will be provided with images, their corresponding captions, in-text mentions, and the Q&A pairs. Your scoring, ranging from 0 to 10, will evaluate the following criteria:

- Scope and Relevance: How well does the question cover key aspects of the medical image and caption provided?
- Value for Fine-Tuning: Is the question formulated in a way that it will add value to the fine-tuning process of the medical LLM?
- Answer Alignment: Does the provided answer directly address the question posed?
- Accuracy: Is the information in the answer medically accurate and correct?
- Utility: How useful is the answer in a medical context? Does it provide actionable or insightful information?
- Image Content Recognition and Utilization: Does the response accurately identify the content depicted in the image and effectively incorporate this information into the answer to enhance comprehension or applicability in a medical context?

Please consider additional factors such as:
- Clarity: Are both the question and the answer clearly articulated and free of ambiguity?
- Detail and Depth: Do the answer's details contribute to a deeper understanding of the topic?
- Medical Precision: How precisely do the question and answer reflect medical terminology and knowledge?

As you review this Q&A pair, Please first output a single line containing one score of this Q&A pair, splited by blank. After that you can give some explanations, like what are the shortcomings of the current instructions"""
    role = 'Assistant'

    @staticmethod
    def conv_to_str(fig_caption, fig_inline_mention, question, answer):
        return (f'[Context]\n'
                f'Figure Caption:\n\t- {fig_caption}\n\n'
                f'Figure Context:\n\t- {fig_inline_mention}\n\n'
                f'Question:\n\t- {question}\n\n'
                f'Answer:\n\t- {answer}\n\n'
                f'[System]\n{LLMEvalPromptGenerator.instruct_prompt}\n\n')

    @staticmethod
    def compare_messages_gen(sample):
        image_path_request = 'path_to_images/' + sample['img']
        base64_image_request = encode_image(image_path_request)
        messages = [
        {"role": "system", "content": """'You are a helpful and precise assistant for checking the quality of the answer."""},
        ]
        messages.append({"role": "user", "content": [
            {"type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_image_request}"}},
            {"type": "text",
            "text": LLMEvalPromptGenerator.conv_to_str(sample['fig_caption'], sample['inline_mention'], sample['question'], sample['answer'])},
          ]})
        return messages

 

def main(args):
    # Load input data
    with open(args.input_path, 'r') as file:
        data = json.load(file)

    output_path = args.output_path

    if os.path.exists(output_path):
        with open(output_path, 'r', encoding='utf-8') as file:
            samples = json.load(file)
    else:
        samples = []


    for i, sample in enumerate(data):
        image_path_request = 'path_to_images/' + sample['img']
        if os.path.exists(image_path_request):

            batch = []
            
            QA1 = {}
            QA1['img'] = sample['img']
            QA1['fig_caption'] = sample['fig_caption']
            QA1['inline_mention'] = sample['inline_mention']
            QA1['question'] = sample['question']
            QA1['answer'] = sample['answer_positive']
            batch.append(QA1)

            print("Q1")
            while True:
                try:
                    async_results = call_async(batch, lambda x: LLMEvalPromptGenerator.compare_messages_gen(x))
                    response = async_results[0]['result'].split('\n')[0]
                    print(response)
                
                    try:
                        # Attempt to parse the first line as an integer score
                        match = re.search(r'\d+', response)
                        if match:
                            first_number = match.group()
                            print("First number found:", first_number)
                        else:
                            print("No number found in the response.")

                        QA1['score'] = int(first_number)
                        break

                    except ValueError:
                        # If there's an error during int conversion, set score to 0
                        QA1['score'] = 0
                        break

                except TimeoutError as e:
                    print("Error in call_async: Request timed out", e)
                    time.sleep(20)
                except requests.exceptions.HTTPError as e:
                    print("Error in call_async: rate limit", e)
                    if response.status_code == 429:
                        time.sleep(20)
                except Exception as e:
                    print("error")
                    time.sleep(20)

            batch = []
            QA2 = {}
            QA2['img'] = sample['img']
            QA2['fig_caption'] = sample['fig_caption']
            QA2['inline_mention'] = sample['inline_mention']
            QA2['question'] = sample['question']
            QA2['answer'] = sample['answer_negative']
            batch.append(QA2)

            while True:
                try:
                    async_results = call_async(batch, lambda x: LLMEvalPromptGenerator.compare_messages_gen(x))
                    response = async_results[0]['result'].split('\n')[0]
                
                    try:
                        # Attempt to parse the first line as an integer score
                        match = re.search(r'\d+', response)
                        if match:
                            first_number = match.group()
                            print("First number found:", first_number)
                        else:
                            print("No number found in the response.")
                        QA2['score'] = int(first_number)
                        break

                    except ValueError:
                        # If there's an error during int conversion, set score to 5
                        QA2['score'] = 5
                        break

                except TimeoutError as e:
                    print("Error in call_async: Request timed out", e)
                    time.sleep(20)
                except requests.exceptions.HTTPError as e:
                    print("Error in call_async: rate limit", e)
                    if response.status_code == 429:
                        time.sleep(20)
                except Exception as e:
                    time.sleep(20)
                
            sample['positive score'] = QA1['score']
            sample['negative score'] = QA2['score']
            
            if QA1['score'] > QA2['score']:
                sample['align'] = 1
            else:
                sample['align'] = 0

            samples.append(sample)

    with open(output_path, 'w', encoding='utf-8') as file:
        json.dump(samples, file, ensure_ascii=False, indent=4)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_path', type=str, default='')
    parser.add_argument('--caption_path', type=str, default='')
    parser.add_argument('--output_path', type=str, default='')
    args = parser.parse_args()
    main(args)
