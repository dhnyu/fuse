# Research Vision

Last updated: 2026-06-09

## Overview

This project investigates how to represent, compare, and retrieve geographical scenes using multimodal representation learning.

For implementation history, completed experiments, design decisions, and current
project status, see [CONTEXT.md](CONTEXT.md). This document focuses on
theoretical motivation, dissertation framing, research questions, and the
long-term scientific vision.

The long-term objective is not merely to generate embeddings for individual buildings, roads, or POIs. Instead, the ultimate goal is to construct meaningful representations of spatial scenes and use those representations to evaluate similarity between regions.

The project is motivated by the observation that humans rarely perceive geographic space as isolated objects. Instead, humans perceive collections of spatial entities that form coherent scenes. A university district, a dense commercial corridor, a suburban residential neighborhood, and a rural village are recognized not because of a single object, but because of the combination of many objects and the spatial relationships among them.

The central research question is therefore:

"Can a machine learn meaningful representations of spatial scenes that preserve geographic structure, semantic meaning, visual context, and spatial relationships?"

The project attempts to answer this question through multimodal embedding fusion and self-supervised contrastive learning.

---

# Theoretical Motivation

## From Spatial Objects to Spatial Scenes

Traditional GIS analysis often operates on predefined spatial units such as:

* buildings
* parcels
* census tracts
* administrative districts

However, human geographic cognition is often scene-based rather than object-based.

A spatial scene can be viewed as a collection of spatial entities organized through spatial relationships.

Examples include:

* university districts
* central business districts
* industrial complexes
* residential neighborhoods
* transportation hubs
* mixed-use urban environments

The same building can have very different meanings depending on the surrounding scene.

Likewise, two regions can appear highly similar despite having no identical buildings.

This suggests that spatial analysis should move beyond individual objects and toward scene-level representations.

---

## Spatial Scene Similarity

Spatial scene similarity refers to the extent to which two scenes share similar:

* spatial structure
* semantic composition
* visual characteristics
* interaction patterns

Historically, scene similarity has been evaluated using manually engineered GIS indicators and rule-based similarity measures.

Such approaches suffer from:

* high computational cost
* subjective feature selection
* limited scalability
* difficulty handling complex spatial relationships

Recent advances in representation learning suggest an alternative approach.

Instead of manually defining similarity, a model can learn latent representations that organize similar scenes close together in embedding space.

This project follows this paradigm.

---

# Research Philosophy

The project is built upon four principles.

## Principle 1: Spatial Information is Multimodal

A spatial object contains multiple dimensions of information.

### Geometry

Examples:

* shape
* area
* perimeter
* footprint structure

### Semantics

Examples:

* business activities
* facilities
* institutions
* land-use functions

### Relations

Examples:

* adjacency
* accessibility
* neighborhood structure
* interactions with surrounding entities

### Visual Context

Examples:

* streetscape appearance
* greenery
* building facades
* commercial intensity

No single modality is sufficient.

Meaningful spatial representations require all modalities to be considered jointly.

---

## Principle 2: Object Embeddings Are Not the Final Goal

Most existing studies stop after generating embeddings for spatial entities.

Examples include:

* building embeddings
* road embeddings
* POI embeddings
* region embeddings

This project treats object embeddings as an intermediate representation.

The final target is scene representation.

Object embeddings are useful because they provide the building blocks from which scene representations can be constructed.

---

## Principle 3: Similarity Should Be Learned Rather Than Defined

Traditional GIS similarity measures require manually specifying:

* weights
* indicators
* similarity functions

This project instead adopts self-supervised contrastive learning.

The objective is to learn a representation space in which:

* similar scenes become close together
* dissimilar scenes become far apart

without requiring manually labeled similarity scores.

---

## Principle 4: Evaluation Must Be Geographic

A representation is useful only if it preserves meaningful geographic information.

Therefore, all embeddings must be validated through downstream tasks and geographic generalization tests.

Simple reconstruction quality is insufficient.

The central question is whether the learned representation captures meaningful geographic structure.

---

# Research Questions

## RQ1: Spatial Entity Representation

How can spatial entities be represented using geometry, semantics, relations, and visual information simultaneously?

### RQ1-1

Can embeddings be generated that preserve all three major dimensions of spatial information?

* geometry
* semantics
* relations

### RQ1-2

What fusion architecture best preserves information across modalities?

### RQ1-3

Can the contribution of each modality be quantified through ablation studies?

### RQ1-4

Are embeddings robust to missing or noisy information?

---

## RQ2: Spatial Scene Representation

How can collections of spatial entities be transformed into scene-level representations?

### RQ2-1

Do scene embeddings preserve both object information and spatial relationships?

### RQ2-2

Which augmentation strategies are most effective for contrastive learning?

### RQ2-3

Do meaningful clusters emerge in representation space?

### RQ2-4

How does scene scale influence representation quality?

### RQ2-5

Do scene embeddings generalize across geographically heterogeneous regions?

---

# Current Project Architecture

The current implementation can be viewed as four layers.

```text
Spatial Objects
       |
       v
Object Embeddings
       |
       v
Scene Embeddings
       |
       v
Scene Similarity Evaluation
```

---

## Layer 1: Spatial Objects

Current data infrastructure includes:

Geometry:

* VWorld buildings

Semantics:

* NGII POIs
* KLIP/UPIS facilities
* OSM POIs
* road networks

Visual Context:

* Google Street View

These datasets collectively provide the multimodal information required for spatial representation learning.

---

## Layer 2: Object Embeddings

Current work focuses primarily on building representations.

Geometry:

* Geo2Vec-based shape embeddings

Semantics:

* planned hybrid semantic embeddings

Visual:

* planned Street View embeddings

The eventual object representation will combine all modalities.

---

## Layer 3: Scene Embeddings

Future work will aggregate object embeddings into scene-level representations.

Potential aggregation strategies include:

* graph neural networks
* graph transformers
* attention pooling
* hierarchical pooling

The exact architecture remains an open research question.

---

## Layer 4: Similarity Learning

Scene embeddings will be optimized using self-supervised contrastive learning.

The intended outcome is a representation space where:

* visually similar scenes cluster together
* semantically similar scenes cluster together
* geographically meaningful patterns emerge naturally

---

# Evolution of the Research Design

## Original Concept (2026-1)

Building source:

* OpenStreetMap buildings

Semantic source:

* OpenStreetMap POIs

Visual source:

* Google Street View

Goal:

* proof-of-concept scene similarity framework

---

## Current Design (2026-06)

Building source:

* VWorld national building database

Semantic sources:

* NGII POIs
* KLIP/UPIS facilities
* OSM POIs
* roads
* administrative context

Visual source:

* Google Street View

Goal:

* large-scale multimodal spatial representation learning

The project has evolved from a relatively simple OSM-based prototype into a nationwide multimodal representation-learning framework.

---

# Current Status

Completed:

* nationwide building infrastructure
* nationwide semantic infrastructure
* Street View acquisition infrastructure
* Geo2Vec validation experiments
* Geo2Vec scaling experiments

In progress:

* semantic embedding generation
* visual embedding generation

Not yet completed:

* scene embedding generation
* contrastive-learning optimization
* similarity evaluation framework
* multimodal fusion

---

# Long-Term Vision

The ultimate output of the project is not a building embedding.

The ultimate output is a spatial-scene representation framework capable of answering questions such as:

* Which regions are most similar to this neighborhood?
* Which urban environments share similar spatial structures?
* Which areas are appropriate matches for policy evaluation?
* Which landscapes belong to the same functional category?
* How can geographic similarity be measured automatically and reproducibly?

The final vision is a general-purpose framework for spatial scene representation and similarity evaluation based on multimodal geospatial data.
