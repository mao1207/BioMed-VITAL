import argparse
import base64
import json
import sys
import time
from collections import defaultdict
from copy import deepcopy
from pprint import pprint

sys.path.append("llava")
from openai_api import call_async


class LLMEvalPromptGenerator:
   

  instruct_prompt = '''Please act as an impartial judge and evaluate the quality of the responses provided by two AI assistants to the user question displayed below. 
Your evaluation should consider correctness and helpfulness. You will be given a reference answer, assistant A's answer, and assistant B's answer. Your job is to evaluate which assistant's answer is better. Begin your evaluation by comparing both assistants’ answers with the reference answer. Identify and correct any mistakes. Avoid any position biases and ensure that the order in which the responses were presented does not influence your decision. 
Do not allow the length of the responses to influence your evaluation. Do not favor certain names of the assistants. Be as objective as possible. 
After providing your explanation, output your final verdict by strictly following this format: "[[A]]" if assistant A is better, "[[B]]"if assistant B is better,and"[[C]]" for a tie. You must begin with [[A]] or [[B]] or [[C]].
 Assigning "[[C]]" should be a last resort, used only if you absolutely cannot discern any difference in the quality of the two responses. 
'''

  role = 'Assistant'

  @staticmethod
  def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

  @staticmethod
  def conv_to_str(question, ground_truth, ans1, ans2):
    return (f'[Context]\n'
            f'[Question]\n{question}\n\n'
            f'[Ground Truth]\n{ground_truth}\n\n'
            f'[{LLMEvalPromptGenerator.role} A]\n{ans1}\n\n[End of {LLMEvalPromptGenerator.role} 1]\n\n'
            f'[{LLMEvalPromptGenerator.role} B]\n{ans2}\n\n[End of {LLMEvalPromptGenerator.role} 2]\n\n')

  @staticmethod
  def compare_messages_gen(sample):
    image_path = args.img_path + sample['image']

    base64_image = LLMEvalPromptGenerator.encode_image(image_path)
    messages = [
      {"role": "system", "content": instruct_prompt}
    ]
    messages.append({"role": "user", "content": [
            {"type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
            {"type": "text",
            "text": LLMEvalPromptGenerator.conv_to_str(sample['question'], sample['ground_truth'], sample['ans1'], sample['ans2'])},
          ],
    
    
    })
    return messages


class ChatEvaluation:
  # Calculate precision, recall, F1 overall and for each domain.

  @staticmethod
  def get_domain(x):
    return x['answer_type']
  
  @staticmethod
  def get_avg(x):
    return sum([float(y) for y in x])/len(x)

  @staticmethod
  def eval(samples):
    predictions = [(x['result'].split('\n')[0].split(' ')) for x in samples]

    tie = 0
    win1 = 0
    win2 = 0

    for scores in predictions:

      if len(scores) == 2:
        a1_score, a2_score = scores
      else:
        a1_score, a2_score = 1, 1
    
      if a1_score > a2_score:
        win1 += 1
      elif a1_score < a2_score:
        win2 += 1
      else:
        tie += 1

    print("win1", win1)
    print("win2", win2)
    print("tie", tie)



def main(args):
  # Load input data
  answer1_data = []
  with open(args.input_path) as f:
    for line in f:
      answer1_data.append(json.loads(line))
    
  answer2_data = []
  with open(args.input_path2) as f:
    for line in f:
      answer2_data.append(json.loads(line))

  question_data = []
  with open(args.question_input_path) as f:
    for line in f:
      question_data.append(json.loads(line))

  # Merge question and answer input data
  samples = []
  for question, answer1, answer2 in zip(question_data, answer1_data, answer2_data):
    sample = deepcopy(question)
    question['question'] = sample['text'][:-8]
    question['ground_truth'] = sample.pop('gpt4_answer')
    question['ans1'] = answer1['text']
    question['ans2'] = answer2['text']
    samples.append(question)
  
  samples_question_ids = set(x['question_id'] for x in samples)

  # Generate GPT-4 evaluation of indivdual answers between model answer and GPT-4 answer
  results = []
  BATCH_SIZE = 1
  for i in range(30):
    result_question_ids = set(result['question_id'] for result in results)

    batch = []
    counter = 0
    for sample in samples:
      if sample['question_id'] in result_question_ids:
        continue
      if sample['answer_type'] == 'CLOSE':
        continue
      batch.append(sample)
      if len(batch)>=BATCH_SIZE:
        try:
          async_results = call_async(batch, lambda x: LLMEvalPromptGenerator.compare_messages_gen(x))
        except:
          continue

        if len(async_results) == 0:
          continue

        # time.sleep(10)
        results.extend(async_results)
        print(async_results)
        print(f"Result Size: {len(results)}")

        batch = []

    try:
      async_results = call_async(batch, lambda x: LLMEvalPromptGenerator.compare_messages_gen(x))
    except:

      continue
    # time.sleep(10)

    results.extend(async_results)
    print(async_results)
    print(f"Result Size: {len(results)}")


  # Print number of questions and results
  print(f'all samples: {len(samples_question_ids)}')
  print(f'ran samples: {len(result_question_ids)}')
  print(f'to be run samples: {len(samples_question_ids-result_question_ids)}')
  
  with open(args.output_path, 'w') as f:
    for line in results:
      f.write(json.dumps(line)+'\n')

  # Perform Evaluation for all results
  ChatEvaluation().eval(results)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--question_input_path', type=str, default='/local/scratch/hcui25/Project/xin/LLaVA-Med/data/VQA-answers/questions2.json')
    parser.add_argument('--input_path', type=str, default='/local/scratch/hcui25/Project/xin/baiduwanpan/pvqa/qas/PathVQA-llava-doctor-13b-filter80-our.jsonl')
    parser.add_argument('--input_path2', type=str, default='/local/scratch/hcui25/Project/xin/baiduwanpan/pvqa/qas/PathVQA-llava-text-13b.jsonl')
    parser.add_argument('--img_path', type=str, default='/local/scratch/hcui25/Project/xin/LLaVA-Med/data/vqa-rad/VQA-RAD-internet/osfstorage-archive/data/test/')
    parser.add_argument('--output_path', type=str, default='/local/scratch/hcui25/Project/xin/LLaVA-Med/data/VQA-answers/llava_med_eval_vision3.jsonl')
    args = parser.parse_args()
    main(args)
