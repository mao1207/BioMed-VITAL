import json
import os
import random
from itertools import product

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
import torchvision.transforms as transforms
from open_clip import (  # works on open-clip-torch>=2.23.0, timm>=0.9.8
    create_model_from_pretrained, get_tokenizer)
from PIL import Image
from sklearn.metrics import (accuracy_score, f1_score, precision_score,
                             recall_score, roc_auc_score)
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm
from transformers import CLIPModel, CLIPProcessor

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


class CustomDataset(Dataset):
    def __init__(self, data_samples, images_folder_path, transform=None):
        self.data_samples = data_samples
        self.images_folder_path = images_folder_path
        self.transform = transform

    def __len__(self):
        return len(self.data_samples)

    def __getitem__(self, idx):
        sample = self.data_samples[idx]

        img_path = os.path.join(self.images_folder_path, sample['image'])
        text = sample['fig_caption'] + sample['in_text_mention'] + "Question:" + sample['conversations'][0]['value'] + "Answer:" + sample['conversations'][1]['value']

        return img_path, text

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor()
])

class BiomedCLIPClassifier(nn.Module):
    def __init__(self, biomedclip_model_name, mlp_hidden_size, num_classes):
        super(BiomedCLIPClassifier, self).__init__()
        # Initialize the processor and model from BiomedCLIP pre-trained weights

        self.biomedclip,  self.processor = create_model_from_pretrained('hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224')
        self.tokenizer = get_tokenizer('hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224')
        # Define a Multilayer Perceptron (MLP) for classification
        # The input size is the sum of the hidden sizes of the text and image features from BiomedCLIP

        self.mlp = nn.Sequential(
            nn.Linear(1024,
                      mlp_hidden_size),
            nn.ReLU(),
            nn.Linear(mlp_hidden_size, mlp_hidden_size),
            nn.ReLU(),
            nn.Linear(mlp_hidden_size, mlp_hidden_size),
            nn.ReLU(),
            nn.Linear(mlp_hidden_size, num_classes),
            nn.Sigmoid()
        )
        
    def forward(self, text_inputs, images):
        # Process the text and image inputs using the BiomedCLIP processor
        # text = self.processor(text=text_inputs, return_tensors="pt", padding=True)
        context_length = 256
        images = torch.stack([self.processor(Image.open(img)) for img in images]).to(device)
        texts = self.tokenizer([template for template in text_inputs], context_length=context_length).to(device) 
        
        image_features, text_features, logit_scale = self.biomedclip(images, texts)

        combined_features = torch.cat((text_features, image_features), dim=1)
        
        # Pass the combined features through the MLP to get classification logits
        logits = self.mlp(combined_features)
        return logits


def load_data(jsonl_path, images_folder_path):

    with open(jsonl_path, 'r', encoding='utf-8') as file:
        data = json.load(file)


    dataset = CustomDataset(data, images_folder_path, transform=transform)
    dataset_loader = DataLoader(dataset, batch_size=100, shuffle=False, num_workers=0)
        
    
    return dataset, dataset_loader, data


def filter(model, dataset_loader, data):

    model.to(device)
    output_scores = torch.tensor([]).to(device)
    
    for images, texts in tqdm(dataset_loader):
        output_score_per_batch = model(texts, images).squeeze().detach()

        if output_score_per_batch.dim() == 0:
            output_score_per_batch = output_score_per_batch.unsqueeze(0)

        output_scores = torch.cat((output_scores, output_score_per_batch))

    sorted_data, indices = torch.sort(output_scores, descending=True)
    indices = indices.tolist()

    # 0.1
    top_10_percent_index = int(0.1 * len(sorted_data))
    top_10_percent_data = [data[i] for i in indices[:top_10_percent_index]]
    with open("top_10.json", 'w', encoding='utf-8') as file:
        json.dump(top_10_percent_data, file, ensure_ascii=False, indent=4)

    # 0.4
    top_40_percent_index = int(0.4 * len(sorted_data))
    top_40_percent_data = [data[i] for i in indices[:top_40_percent_index]]
    with open("top_40.json", 'w', encoding='utf-8') as file:
        json.dump(top_40_percent_data, file, ensure_ascii=False, indent=4)

    # 0.8
    top_80_percent_index = int(0.8 * len(sorted_data))
    top_80_percent_data = [data[i] for i in indices[:top_80_percent_index]]
    with open("top_80.json", 'w', encoding='utf-8') as file:
        json.dump(top_80_percent_data, file, ensure_ascii=False, indent=4)

    # 0.9
    top_90_percent_index = int(0.9 * len(sorted_data))
    top_90_percent_data = [data[i] for i in indices[:top_90_percent_index]]
    with open("top_90.json", 'w', encoding='utf-8') as file:
        json.dump(top_90_percent_data, file, ensure_ascii=False, indent=4)




# Define hyperparameters
biomedclip_model_name = 'microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224'

mlp_hidden_size = 512
num_classes = 1  # If it's a binary classification task, you might only need one output (good vs bad answer)

# Instantiate the model

# Specify the path to your .jsonl file and the directory containing the images
jsonl_file_path = 'path_to_score_json'
images_folder_path = 'path_to_imgs'

model = BiomedCLIPClassifier(biomedclip_model_name, mlp_hidden_size, num_classes)
model.load_state_dict(torch.load('', map_location=device))

# Load the data
dataset, dataset_loader, data = load_data(jsonl_file_path, images_folder_path)

filter(model, dataset_loader, data)
