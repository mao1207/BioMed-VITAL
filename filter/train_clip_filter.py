import json
import os
import random
from itertools import product

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

model_save_path = ''


class CustomDataset(Dataset):
    def __init__(self, data_samples, images_folder_path, weight, transform=None):
        self.data_samples = data_samples
        self.images_folder_path = images_folder_path
        self.transform = transform
        self.weight = weight

    def __len__(self):
        return len(self.data_samples)

    def __getitem__(self, idx):
        sample = self.data_samples[idx]
        if 'question' in sample:
            img_path_positive = os.path.join(self.images_folder_path, sample['img'])
            image_positive = img_path_positive
            img_path_negative = os.path.join(self.images_folder_path, sample['img'])
            image_negative = img_path_negative
            positive = "Question:" + sample['question'] + "Answer:" + sample['answer_positive']
            negative = "Question:" + sample['question'] + "Answer:" + sample['answer_negative']
            
            return image_positive, positive, 1, image_negative, negative, 0, self.weight

        else:
            img_path1 = os.path.join(self.images_folder_path, sample[0]['image'])
            image1 = img_path1
            score1 = sample[0]['score']
            text1 = sample[0]['text']
            img_path2 = os.path.join(self.images_folder_path, sample[1]['image'])
            image2 = img_path2
            score2 = sample[1]['score']
            text2 = sample[1]['text']

        return image1, text1, score1, image2, text2, score2, 1

class CustomDatasetTEST(Dataset):
    def __init__(self, data_samples, images_folder_path, transform=None):
        self.data_samples = data_samples
        self.images_folder_path = images_folder_path
        self.transform = transform

    def __len__(self):
        return len(self.data_samples)

    def __getitem__(self, idx):
        sample = self.data_samples[idx]
        img_path_positive = os.path.join(self.images_folder_path, sample['img_positive'])
        image_positive = img_path_positive
        img_path_negative = os.path.join(self.images_folder_path, sample['img_negative'])
        image_negative = img_path_negative
        positive = sample['fig_caption_positive'] + sample['inline_mention_positive'] + "Question:" + sample['question_positive'] + "Answer:" + sample['answer_positive']
        negative = sample['fig_caption_negative'] + sample['inline_mention_negative'] + "Question:" + sample['question_negative'] + "Answer:" + sample['answer_negative']

        return image_positive, image_negative, positive, negative

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

def split_data(rank_data, train_num, test_num):
    train_samples = []
    test_samples = []
    all_samples = []

    score_levels = list(rank_data.keys())

    if len(score_levels) < 2:
        raise ValueError("At least two different score levels are needed to generate sample pairs")

    for _ in range(train_num):
        while True:
            score1, score2 = random.sample(score_levels, 2)
            print(len(rank_data[score1]) * 4 // 5)
            print(len(rank_data[score1]))
            print(len(rank_data[score2]) * 4 // 5)
            print(len(rank_data[score2]))
            if len(rank_data[score1]) == 1 or len(rank_data[score2]) == 1:
                continue
            break

        item1 = random.choice(rank_data[score1][:len(rank_data[score1]) * 4 // 5])
        item2 = random.choice(rank_data[score2][:len(rank_data[score2]) * 4 // 5])
        all_samples.append(item1)
        all_samples.append(item2)
        train_samples.append((item1, item2))

    for _ in range(test_num):
        while True:
            score1, score2 = random.sample(score_levels, 2)
            print(len(rank_data[score1]) * 4 // 5)
            print(len(rank_data[score1]))
            print(len(rank_data[score2]) * 4 // 5)
            print(len(rank_data[score2]))
            if len(rank_data[score1]) == 1 or len(rank_data[score2]) == 1:
                continue
            break
        item1 = random.choice(rank_data[score1][len(rank_data[score1]) * 4 // 5:])
        item2 = random.choice(rank_data[score2][len(rank_data[score2]) * 4 // 5:])
        if item1 in all_samples or item2 in all_samples:
            continue
        test_samples.append((item1, item2))

    return train_samples, test_samples


def load_data(gpt_file_path, human_file_path, images_folder_path, weight):

    with open(gpt_file_path, 'r', encoding='utf-8') as file:
        gpt_data = json.load(file)

    rank_data = {}
    for score in gpt_data.keys():
        rank_data[score] = []
        for i, sample in enumerate(gpt_data[score]):
            item = {}
            item['image'] = sample['image']
            item['text'] = sample['fig_caption'] + sample['in_text_mention'] + "Question:" + sample['conversations'][0]['value'] + "Answer:" + sample['conversations'][1]['value']
            item['score'] = int(score)
            rank_data[score].append(item)

    train_samples, test_samples = split_data(rank_data, 30000, 10000)

    with open(human_file_path, 'r', encoding='utf-8') as file:
        human_data = json.load(file)[:50]

    train_samples.extend(human_data)

    train_dataset = CustomDataset(train_samples, images_folder_path, weight, transform=transform)
    test_dataset = CustomDataset(test_samples, images_folder_path, weight, transform=transform)

    train_loader = DataLoader(train_dataset, batch_size=64, shuffle=True, num_workers=0)
    test_loader = DataLoader(test_dataset, batch_size=32, shuffle=True, num_workers=0)
        
    
    return train_dataset, test_dataset, train_loader, test_loader

def load_test(jsonl_file_path, images_folder_path, num=None):
    with open(jsonl_file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    if num is not None:
        data = random.sample(data, min(num, len(data)))

    test_dataset = CustomDatasetTEST(data, images_folder_path, transform=transform)
    test_loader = DataLoader(test_dataset, batch_size=32, shuffle=True, num_workers=0)

    return test_dataset, test_loader


def rank_loss(output1, output2, scores1, scores2, weight):
    sigmoid = torch.sigmoid

    score_diffs = scores1 - scores2

    output_diffs = output1 - output2

    zi = (score_diffs >= 0).float()
    zj = (score_diffs < 0).float()

    weight = weight.to(device)
    loss = (-zi * torch.log(sigmoid(output1 - output2)) - zj * torch.log(sigmoid(output2 - output1))) * weight

    return loss.mean()

def hinge_loss(output1, output2, scores1, scores2, weight, margin = 1):
    score_diffs = scores1 - scores2

    output_diffs = output1 - output2

    # y is 1 if scores1 > scores2, else -1
    y = torch.where(score_diffs > 0, torch.tensor(1.0).to(output1.device), torch.tensor(-1.0).to(output1.device))

    hinge_loss = torch.max(torch.tensor(0.0).to(output1.device), margin - y * output_diffs)

    loss = hinge_loss * weight.to(device)

    return loss.mean()


def train(model, train_loader, test_loader, align_test_loader):

    model.to(device)
    for name, param in model.named_parameters():
        print(f"{name}: shape = {param.shape}")

    num_epochs = 6

    optimizer = optim.Adam(model.parameters(), lr=0.00001)
    

    model.train()
    for epoch in range(num_epochs):
        total_loss = 0
        train_loader = tqdm(train_loader, desc=f'Train Stage: Epoch {epoch+1}/{num_epochs}')
        for images1, texts1, scores1, images2, texts2, scores2, weight in train_loader:
            scores1 = scores1.to(device)
            scores2 = scores2.to(device)
            
            optimizer.zero_grad()
            outputs1 = model(texts1, images1).squeeze()
            outputs2 = model(texts2, images2).squeeze()

            loss = hinge_loss(outputs1, outputs2, scores1, scores2, weight)
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            
        avg_loss = total_loss / len(train_loader)
        print(f'Epoch [{epoch+1}/{num_epochs}], Train Loss: {avg_loss:.4f}')


        optimizer.zero_grad()
        torch.cuda.empty_cache()
        model.eval()

        success_rates = []
        for images1, texts1, scores1, images2, texts2, scores2, weight in test_loader:
            scores1 = scores1.to(device)
            scores2 = scores2.to(device)
            
            optimizer.zero_grad()
            outputs1 = model(texts1, images1).squeeze()
            outputs2 = model(texts2, images2).squeeze()

            success_rate = torch.sum((outputs1 - outputs2) * (scores1 - scores2) > 0) / outputs1.shape[0]
            success_rates.append(success_rate)

        print("Test Success Rate: ", sum(success_rates)/len(success_rates))
        torch.cuda.empty_cache()

        success_rates = []
        predicted_scores = []
        true_labels = []
        global_positives = []
        global_negatives = []
        for img_positives, img_negatives, positives, negatives in align_test_loader:
            outputs_positive = model(positives, img_positives).squeeze().detach()
            outputs_negative = model(negatives, img_negatives).squeeze().detach()
            success_rate = torch.sum(outputs_positive > outputs_negative) / outputs_negative.shape[0]
            success_rates.append(success_rate)

            predicted_scores.append(outputs_positive)
            true_labels.append(torch.ones(outputs_positive.shape[0], dtype=torch.int).to(device))
            predicted_scores.append(outputs_negative)
            true_labels.append(torch.zeros(outputs_negative.shape[0], dtype=torch.int).to(device))

            global_positives.append(outputs_positive)
            global_negatives.append(outputs_negative)


        predicted_scores = torch.cat(predicted_scores).cpu().numpy()
        true_labels = torch.cat(true_labels).cpu().numpy()

        # Merge global positive and negative sample scores
        global_positives = torch.cat(global_positives)
        global_negatives = torch.cat(global_negatives)

        # Calculate Global Mean Rank
        positive_mask = torch.cat((torch.ones_like(global_positives), torch.zeros_like(global_negatives))).bool()
        all_scores = torch.cat((global_positives, global_negatives))
        sorted_scores, indices = torch.sort(all_scores, descending=True)
        ranks = torch.nonzero(positive_mask[indices]).squeeze()
        mean_rank = ranks.float().mean().item() / indices.shape[0]

        # Calaulate MAP
        precisions_at_k = []
        for rank in ranks:
            precisions_at_k.append((ranks <= rank).float().sum().item() / (rank.item() + 1))

        ap = torch.tensor(precisions_at_k).mean().item()  # Average Precision for each positive sample
        map_score = ap  # Mean Average Precision across all positives

        print("Alignment Rate: ", sum(success_rates)/len(success_rates))
        print("Alignment AUC: ", roc_auc_score(true_labels, predicted_scores))
        print("Global Mean Rank: ", mean_rank)
        print("Global MAP: ", map_score)

        alignment_rate = sum(success_rates)/len(success_rates)
        # if alignment_rate > 0.64:
        #     torch.save(model.state_dict(), model_save_path)
        #     print(f"Model saved successfully at {model_save_path}")

        optimizer.zero_grad()
        torch.cuda.empty_cache()



# Define hyperparameters
biomedclip_model_name = 'microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224'

mlp_hidden_size = 512
num_classes = 1  # If it's a binary classification task, you might only need one output (good vs bad answer)

# Instantiate the model

# Specify the path to your .jsonl file and the directory containing the images
jsonl_file_path = 'merged_data.json'
images_folder_path = 'path_to_images'
align_test_file_path = 'test.json'

weights = [1, 10, 100, 200, 300, 400]

for weight in weights:
    print(weight)
    model = BiomedCLIPClassifier(biomedclip_model_name, mlp_hidden_size, num_classes)
    align_train_file_path = 'train.json'

    # Load the data
    train_dataset, test_dataset, train_loader, test_loader = load_data(jsonl_file_path, align_train_file_path, images_folder_path, weight)
    align_test_dataset, align_test_loader = load_test(align_test_file_path, images_folder_path, 2000)

    train(model, train_loader, test_loader, align_test_loader)
