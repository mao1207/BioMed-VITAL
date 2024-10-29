import argparse
import base64
import hashlib
import itertools
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import openai
import torch
import torch.nn.functional as F
import torchvision.transforms as transforms
from openai import AzureOpenAI
from PIL import Image
from sklearn.cluster import KMeans
from transformers import ViTFeatureExtractor, ViTModel

parser = argparse.ArgumentParser(description='ChatGPT-based QA evaluation.')
parser.add_argument('--processes_sum', type=int, default=4)
parser.add_argument('--processes_id', type=int, default=0)
parser.add_argument('--img_dir', type=str, default="/local/scratch/hcui25/Project/xin/LLaVA-Med/data/images/")
parser.add_argument('--output_dir', type=str, default="/local/scratch/hcui25/Project/xin/LLaVA-Med/data/instruct/vision_instruction.json")
parser.add_argument('--api_version', type=str, default="")
parser.add_argument('--azure_endpoint', type=str, default="")
parser.add_argument('--api_key', type=str, default="")
args = parser.parse_args()

client = AzureOpenAI(api_version=args.api_version,
azure_endpoint=args.azure_endpoint,
api_key=args.api_key)

json_file_path = '/local/scratch/hcui25/Project/xin/LLaVA-Med/data/instruct/llava_med_instruct_fig_captions.json'
img_dir = args.img_dir
with open(json_file_path) as f:
    domain_dict = json.load(f)

cluster_vectors = []
contents = []

feature_extractor = ViTFeatureExtractor.from_pretrained('google/vit-base-patch16-224-in21k')
model = ViTModel.from_pretrained('google/vit-base-patch16-224-in21k')

for cycle_idx, samples in enumerate(itertools.zip_longest(*domain_dict.values())):
    
    for domain_idx, content in enumerate(samples):
        if content is not None:
            imgs_request = img_dir + content['pair_id'] + ".jpg"
        else:
            imgs_request = "none"


        if os.path.exists(imgs_request) and content['domain']['gross'] == False and content['domain']['histology'] == False:

            # Define a transformation sequence to process the image
            contents.append(content)
            transform_pipeline = transforms.Compose([
                transforms.Lambda(lambda x: x.convert('RGB'))
            ])

            # Read the image and apply the conversion
            with open(imgs_request, 'rb') as image_file:
                image = transform_pipeline(Image.open(image_file))
                inputs = feature_extractor(images=image, return_tensors="pt")
                outputs = model(**inputs)
                embedding = outputs.last_hidden_state
                pooled_output = F.avg_pool2d(embedding, kernel_size=6, stride=6)
                image_vector = pooled_output.flatten(start_dim=1)
                image_vector = np.array(image_vector.squeeze().detach())

            fig_caption = content['fig_caption']
            if content['in_text_mention'] == None:
                in_text_mention = ""
            else:
                in_text_mention = content['in_text_mention'][0]['tokens']
            input_text = fig_caption + in_text_mention

            response = client.embeddings.create(input = input_text, model="text-embedding-ada-002").data[0].embedding
            response.extend(image_vector)
            cluster_vectors.append(response)
            print("=====================================", flush=True)
            print(len(cluster_vectors), flush=True)
            
            if len(cluster_vectors) % 1000 == 0:
                num_clusters = 60
                contents_all_classes = {}

                # Create a KMeans Instance
                kmeans = KMeans(n_clusters=num_clusters)

                # cluster
                kmeans.fit(cluster_vectors)
                print(kmeans.labels_)

                for i in range(num_clusters):
                    contents_all_classes[i] = []

                for i, content in enumerate(contents):
                    contents_all_classes[kmeans.labels_[i]].append(content)

                json_path = "/local/scratch/hcui25/Project/xin/LLaVA-Med/data/instruct/cluster_contents.json"
                with open(json_path, "w") as json_file:
                    json.dump(contents_all_classes, json_file, indent=4)




