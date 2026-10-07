# Parser comparison: attention-is-all-you-need

## baseline
- raw chars: 2022
- cleaned chars: 2022
- structure items: 5
- parse seconds: 0.001
- title: Attention Is All You Need — paper explained | Example Blog
- metadata: {"description": "A plain-English walkthrough of the Transformer architecture and self-attention."}

```text
Attention Is All You Need — paper explained
 Published on 2017-06-12 · 12 min read
 Why the paper mattered
 Before 2017, nearly every state-of-the-art sequence model was built on recurrent networks. RNNs process tokens one at a time, which creates two problems: the path between distant tokens is long, so gradients get weak, and the sequential nature of the computation prevents parallel processing of a sequence during training.
 The Transformer replaces recurrence entirely with attention. Every position in the sequence can attend to every other position in a single step, so the distance between two tokens no longer affects how easily information flows between them.
 Self-attention in one paragraph
 Each token emits three vectors: a query, a key and a value. The query of one token is compared against the keys of all tokens to produce a set of attention weights, and those weights define a weighted sum of the values. That sum is the token's new representation, enriched with context from the rest of the sequence.
 Multi-head attention runs this process several times in parallel with different projection matrices. One head may learn to track syntactic dependencies while another tracks co
```

## trafilatura
- raw chars: 2025
- cleaned chars: 2001
- structure items: 5
- parse seconds: 0.027
- title: Attention Is All You Need — paper explained
- metadata: {"title": "Attention Is All You Need \u2014 paper explained", "author": "Published", "url": "attention-is-all-you-need", "description": "A plain-English walkthrough of the Transformer architecture and self-attention.", "date": "2017-06-12", "raw_text": "Attention Is All You Need \u2014 paper explained\nWhy the paper mattered\nBefore 2017, nearly every state-of-the-art sequence model was built on r

```text
# Attention Is All You Need — paper explained
 ## Why the paper mattered
 Before 2017, nearly every state-of-the-art sequence model was built on recurrent networks. RNNs process tokens one at a time, which creates two problems: the path between distant tokens is long, so gradients get weak, and the sequential nature of the computation prevents parallel processing of a sequence during training.
 The Transformer replaces recurrence entirely with attention. Every position in the sequence can attend to every other position in a single step, so the distance between two tokens no longer affects how easily information flows between them.
 ## Self-attention in one paragraph
 Each token emits three vectors: a query, a key and a value. The query of one token is compared against the keys of all tokens to produce a set of attention weights, and those weights define a weighted sum of the values. That sum is the token's new representation, enriched with context from the rest of the sequence.
 Multi-head attention runs this process several times in parallel with different projection matrices. One head may learn to track syntactic dependencies while another tracks coreference, and the outputs of a
```

## docling
- not installed (docling is not installed -> run: uv sync --extra docling  (heavy: downloads models))

## unstructured
- raw chars: 2022
- cleaned chars: 2022
- structure items: 5
- parse seconds: 1.044
- title: Attention Is All You Need — paper explained
- metadata: {"element_counts": {"Title": 5, "NarrativeText": 7}, "elements": 12}

```text
Attention Is All You Need — paper explained
 Published on 2017-06-12 · 12 min read
 Why the paper mattered
 Before 2017, nearly every state-of-the-art sequence model was built on recurrent networks. RNNs process tokens one at a time, which creates two problems: the path between distant tokens is long, so gradients get weak, and the sequential nature of the computation prevents parallel processing of a sequence during training.
 The Transformer replaces recurrence entirely with attention. Every position in the sequence can attend to every other position in a single step, so the distance between two tokens no longer affects how easily information flows between them.
 Self-attention in one paragraph
 Each token emits three vectors: a query, a key and a value. The query of one token is compared against the keys of all tokens to produce a set of attention weights, and those weights define a weighted sum of the values. That sum is the token's new representation, enriched with context from the rest of the sequence.
 Multi-head attention runs this process several times in parallel with different projection matrices. One head may learn to track syntactic dependencies while another tracks co
```
