# Biomedical Visual Instruction Tuning with Clinician Preference Alignment

Authors: Hejie Cui*, Lingjun Mao*, Xin Liang, Jieyu Zhang, Hui Ren, Quanzheng Li, Xiang Li, Carl Yang

---

![Biomed-VITAL Framework Overview](https://raw.githubusercontent.com/BioMed-VITAL/BioMed-VITAL.github.io/main/images/updated_instruction_data_framework_00.png) 

## Abstract

Recent advancements in multimodal foundation models have showcased impressive capabilities in understanding and reasoning with visual and textual information. Adapting these foundation models trained for general usage to specialized domains like biomedicine requires large-scale domain-specific instruction datasets. While existing works have explored curating such datasets automatically, the resultant datasets are not explicitly aligned with domain expertise.

In this work, we propose a data-centric framework, **Biomedical Visual Instruction Tuning with Clinician Preference Alignment (BioMed-VITAL)**, that incorporates clinician preferences into both stages of generating and selecting instruction data for tuning biomedical multimodal foundation models. During the generation stage, we prompt the GPT-4V generator with a diverse set of clinician-selected demonstrations for preference-aligned data candidate generation. Then, during the selection phase, we train a separate selection model, which explicitly distills clinician and policy-guided model preferences into a rating function to select high-quality data for medical instruction tuning.

Results show that the model tuned with the instruction-following data from our method demonstrates a significant improvement in open visual chat (18.5% relatively) and medical VQA (win rate up to 81.73%).

## Contributions

1. We introduce a data-centric framework **BioMed-VITAL**, which generates and selects instruction-following data aligned with clinician preference for visual instruction tuning. Evaluation indicates an improved data quality and our instruction-tuned models remarkably improve in both open visual chat (18.5% relatively) and three biomedical VQA benchmarks (win rate up to 81.73%).
2. We propose a paradigm involving clinician preference during generation and an effective data selection model based on a mixture of preferences. It is shown that our distilled data selection model excels in matching human preferences compared with judgments of GPT-4.
3. To facilitate further study, we release 80K clinician preference-aligned instruction-following datasets generated and selected from ours, along with the models instruction-tuned based on them.

## Dataset

Based on the PMC-15 dataset, we utilized the `gpt-4-vision-preview` API to generate multi-round QA instructional data and conducted a two-stage clinician preference alignment process, selecting 60K and 80K language-image instruction-following samples. Additionally, we combined the filtered 80K samples with 10K and 60K samples provided by LLaVA-Med, resulting in a larger dataset of 150K samples (80K+10K+60K). We also offer an intermediate dataset of 60K samples that only incorporates the second stage of preference distillation, merging these to form a dataset of 210K samples (80K+10K+60K+60K).

You can access the dataset on [HuggingFace Dataset](https://huggingface.co/datasets/mao1207/BioMed-VITAL-instructions).

### BioMed-VITAL Instructions Files

| Data file name                                                                 | File Size | Sample Size        |
| ------------------------------------------------------------------------------ | --------- | ------------------ |
| [BioMed-VITAL-instructions-60K.json](https://huggingface.co/datasets/mao1207/BioMed-VITAL-instructions/blob/main/BioMed-VITAL-instructions-60K.json) | 127 MB     | 60K                 |
| [BioMed-VITAL-instructions-80K.json](https://huggingface.co/datasets/mao1207/BioMed-VITAL-instructions/blob/main/BioMed-VITAL-instructions-80K.json) | 156 MB     | 80K                 |
| [BioMed-VITAL-instructions-150K.json](https://huggingface.co/datasets/mao1207/BioMed-VITAL-instructions/blob/main/BioMed-VITAL-instructions-150K.json) | 309 MB     | 60K + 10K + 80K     |
| [BioMed-VITAL-instructions-210K.json](https://huggingface.co/datasets/mao1207/BioMed-VITAL-instructions/blob/main/BioMed-VITAL-instructions-210K.json) | 463 MB     | 80K + 10K + 60K + 60K |

### Original Images

You can download the original images from the following link:

| Data file name                                                              | File Size |
| ---------------------------------------------------------------------------- | --------- |
| [PMC_image_urls.jsonl](https://github.com/mao1207/BioMed-VITAL/blob/main/data/PMC_image_urls.jsonl) | 129 MB     |

## License

The source code of this repository is released under the Apache License 2.0. The model license and dataset license are listed on their corresponding webpages.

---

## Case Study
### Biomedical Visual Instruction-Following Example
![](https://raw.githubusercontent.com/BioMed-VITAL/BioMed-VITAL.github.io/main/images/case_update2_00.png) 
### Biomedical VQA Benchmark
![](https://raw.githubusercontent.com/BioMed-VITAL/BioMed-VITAL.github.io/main/images/case5_updated_00.png) 
### Clinician Annotation Examples
![](https://raw.githubusercontent.com/BioMed-VITAL/BioMed-VITAL.github.io/main/images/appendixH_00.png) 

For more information, access to the dataset, and to contribute, please visit our [Website](https://biomed-vital.github.io/).
