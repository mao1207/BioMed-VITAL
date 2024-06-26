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
   
  instruct_prompt = """We request your assessment of the performance of two AI assistants 
  based on their responses to a user's question about an image and its context. 
  You will be given the image, and you will have additional text (Figure Context) that mentions the image. 
  Please evaluate the helpfulness, relevance, accuracy, and detail in their answers. 
  Assign an overall score to each assistant on a scale from 1 to 10, 
  where a higher score reflects superior overall performance. Begin with a single line containing two scores 
  separated by a space for Assistant 1 and Assistant 2, respectively. 
  Then provide a detailed justification for your scores, ensuring an impartial evaluation that 
  is not influenced by the sequence in which the responses were given."""
  role = 'Assistant'

  @staticmethod
  def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

  @staticmethod
  def conv_to_str(fig_label, fig_caption, fig_inline_mention, question, ans1, ans2):
    return (f'[Context]\n'
            f'Figure Caption:\n{fig_label}: {fig_caption}\n\n'
            f'Figure Context:\n\t- {fig_inline_mention}\n\n'
            f'[Question]\n{question}\n\n'
            f'[{LLMEvalPromptGenerator.role} 1]\n{ans1}\n\n[End of {LLMEvalPromptGenerator.role} 1]\n\n'
            f'[{LLMEvalPromptGenerator.role} 2]\n{ans2}\n\n[End of {LLMEvalPromptGenerator.role} 2]\n\n'
            f'[System]\n{LLMEvalPromptGenerator.instruct_prompt}\n\n')

  @staticmethod
  def compare_messages_gen(sample):
    image_path = args.img_path + sample['image']

    base64_image = LLMEvalPromptGenerator.encode_image(image_path)
    messages = [
    {"role": "system", "content": """'"You are a helpful and precise assistant for checking the quality of the answer."""},
    ]
    messages.append({"role": "user", "content": [
            {"type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
            {"type": "text",
            "text": LLMEvalPromptGenerator.conv_to_str(sample['fig_label'], sample['fig_caption'], sample['in_text_mention'], sample['question'], sample['ans1'], sample['ans2'])},
          ],
    
    
    })
    return messages


class ChatEvaluation:
  # Calculate precision, recall, F1 overall and for each domain.

  @staticmethod
  def get_domain(x):
    for domain in ['chest_xray', 'mri', 'histology', 'gross', 'ct_scan']:
      in_domain = x['domain'][domain]
      if in_domain:
        return domain
  
  @staticmethod
  def get_avg(x):
    return sum([float(y) for y in x])/len(x)

  @staticmethod
  def eval(samples):
    predictions = [(x['question_id'], x['type'], ChatEvaluation.get_domain(x), x['result'].split('\n')[0].split(' ')) for x in samples]
    score_type_dict = defaultdict(lambda: defaultdict(list))
    print(predictions)
    for q_id, q_type, domain, scores in predictions:

      if len(scores) == 2:
        a1_score, a2_score = scores
      else:
        a1_score, a2_score = 1, 1

      score_type_dict[q_type][1].append(a1_score)
      score_type_dict[q_type][2].append(a2_score)
      score_type_dict['all'][1].append(a1_score)
      score_type_dict['all'][2].append(a2_score)
      score_type_dict[domain][1].append(a1_score)
      score_type_dict[domain][2].append(a2_score)

    result = defaultdict(dict)

    for q_type, score_dict in score_type_dict.items():
      result[q_type]['gpt4_score'] = ChatEvaluation.get_avg(score_dict[1])
      result[q_type]['pred_score'] = ChatEvaluation.get_avg(score_dict[2])
      result[q_type]['pred_relative_score'] = ChatEvaluation.get_avg([float(s2)/float(s1) for s1, s2 in zip(score_dict[1], score_dict[2])])*100
      result[q_type]['data_size'] = len(score_dict[1])
    # print results 
    pprint(result)


def main(args):
  # Load input data
  answer_data = []
  with open(args.input_path) as f:
    for line in f:
      answer_data.append(json.loads(line))

  question_data = []
  with open(args.question_input_path) as f:
    for line in f:
      question_data.append(json.loads(line))

  # Merge question and answer input data
  samples = []
  for question, answer in zip(question_data, answer_data):
    sample = deepcopy(question)
    question['question'] = sample['text'][:-8]
    question['ans1'] = sample.pop('gpt4_answer')
    question['ans2'] = answer['text']
    samples.append(question)
  
  samples_question_ids = set(x['question_id'] for x in samples)

  # Generate GPT-4 evaluation of indivdual answers between model answer and GPT-4 answer
  results = []
  BATCH_SIZE = 3
  for i in range(30):
    result_question_ids = set(result['question_id'] for result in results)

    batch = []
    counter = 0
    for sample in samples:
      if sample['question_id'] in result_question_ids:
        continue
      batch.append(sample)
      if len(batch)>=BATCH_SIZE:
        async_results = call_async(batch, lambda x: LLMEvalPromptGenerator.compare_messages_gen(x))
        # time.sleep(10)
        results.extend(async_results)
        print(f"Result Size: {len(results)}")
        batch = []
    async_results = call_async(batch, lambda x: LLMEvalPromptGenerator.compare_messages_gen(x))
    # time.sleep(10)
    results.extend(async_results)
    print(f"Result Size: {len(results)}")
    
  # Print number of questions and results
  print(f'all samples: {len(samples_question_ids)}')
  print(f'ran samples: {len(result_question_ids)}')
  print(f'to be run samples: {len(samples_question_ids-result_question_ids)}')

  # # Write GPT-4 evaluation outputs to output_path
  # results = []
  # with open(args.output_path, 'r') as f:
  #   for line in f:
  #     data = json.loads(line)
  #     results.append(data)

  
  with open(args.output_path, 'w') as f:
    for line in results:
      f.write(json.dumps(line)+'\n')

  # Perform Evaluation for all results
  ChatEvaluation().eval(results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--question_input_path', type=str, default='data/eval/llava_med_eval_qa50_qa.jsonl')
    parser.add_argument('--input_path', type=str, default='dbfs:/mnt/hanoverdev/scratch/clwon/llava/test/answers/test50/2023-05-10_med-pretrain-364m-v1-1epoch.jsonl')
    parser.add_argument('--img_path', type=str, default='/local/scratch/hcui25/Project/xin/LLaVA-Med/data/images/')
    parser.add_argument('--output_path', type=str, default='data/eval/llava_med_eval_qa50_qa_ans.jsonl')
    args = parser.parse_args()
    main(args)
