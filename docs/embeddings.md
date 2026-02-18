# Embedding Model Selection Guide

This guide helps you choose the right embedding model for your Canopy Research deployment based on your performance, quality, and resource requirements.

## Default Model

**`all-mpnet-base-v2`** is the default model, optimized for document similarity and clustering tasks. It provides the best balance of quality and performance for blog posts, articles, and similar content.

## Model Comparison

### Recommended Models

#### 1. `all-mpnet-base-v2` (Default) ⭐

**Best for:** Document clustering, centroid similarity, semantic search

- **Dimensions:** 768
- **Parameters:** ~110M
- **Architecture:** MPNet (12 transformer layers)
- **Speed:** Baseline (1x)
- **Quality:** Highest quality for general-purpose embeddings
- **Use case:** Production deployments prioritizing accuracy

**Why it's the default:**
- Superior semantic understanding for document-level tasks
- Better context capture for longer documents (up to 10,000 characters)
- Higher dimensional embeddings capture nuanced relationships
- Excellent performance on clustering and similarity benchmarks

**Trade-offs:**
- Slower than MiniLM models (~5x)
- Higher memory usage (~420MB)
- More CPU/GPU resources required

---

#### 2. `all-MiniLM-L6-v2`

**Best for:** Resource-constrained environments, high-throughput scenarios

- **Dimensions:** 384
- **Parameters:** ~22M
- **Architecture:** Distilled MiniLM (6 transformer layers)
- **Speed:** ~5x faster than all-mpnet-base-v2
- **Quality:** Good quality, suitable for most use cases
- **Use case:** Development, testing, or deployments with limited resources

**When to use:**
- Limited CPU/memory resources
- Need to process large volumes quickly
- Quality requirements are moderate
- Running on edge devices or small servers

**Trade-offs:**
- Lower dimensional embeddings (384 vs 768)
- May miss subtle semantic relationships
- Less effective for complex document clustering

**Configuration:**
```bash
export EMBEDDING_MODEL="all-MiniLM-L6-v2"
```

---

#### 3. `all-MiniLM-L12-v2`

**Best for:** Balance between speed and quality

- **Dimensions:** 384
- **Parameters:** ~33M
- **Architecture:** Distilled MiniLM (12 transformer layers)
- **Speed:** ~3x faster than all-mpnet-base-v2
- **Quality:** Better than L6-v2, but still lower than mpnet-base-v2
- **Use case:** When you need better quality than L6-v2 but faster than mpnet-base-v2

**Trade-offs:**
- Still 384 dimensions (same as L6-v2)
- Better quality than L6-v2 but slower
- Not as accurate as mpnet-base-v2

**Configuration:**
```bash
export EMBEDDING_MODEL="all-MiniLM-L12-v2"
```

---

### Specialized Models

#### `multi-qa-mpnet-base-dot-v1`

**Best for:** Question-answering, semantic search with queries

- **Dimensions:** 768
- **Parameters:** ~110M
- **Trained on:** 215M question-answer pairs
- **Use case:** When your primary use case is semantic search with user queries

**Note:** This model is optimized for query-document matching, not document-document similarity. May not perform as well for clustering tasks.

---

## Performance Benchmarks

Based on the Massive Text Embedding Benchmark (MTEB) and real-world usage:

| Model | Clustering Quality | Speed | Memory | Dimensions |
|-------|-------------------|-------|--------|------------|
| `all-mpnet-base-v2` | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | 768 |
| `all-MiniLM-L12-v2` | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 384 |
| `all-MiniLM-L6-v2` | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 384 |

## Configuration

### Environment Variable

Set the model via the `EMBEDDING_MODEL` environment variable:

```bash
# Use default (all-mpnet-base-v2)
# No configuration needed

# Use MiniLM for faster processing
export EMBEDDING_MODEL="all-MiniLM-L6-v2"

# Use MiniLM-L12 for balanced performance
export EMBEDDING_MODEL="all-MiniLM-L12-v2"
```

### Programmatic Configuration

```python
from canopyresearch.services.embeddings import LocalEmbeddingBackend

# Use default model
backend = LocalEmbeddingBackend()

# Use specific model
backend = LocalEmbeddingBackend(model_name="all-MiniLM-L6-v2")
```

## Migration Guide

### Upgrading from `all-MiniLM-L6-v2` to `all-mpnet-base-v2`

If you're upgrading from the previous default:

1. **Embedding Dimensions Change:** 384 → 768
   - Existing embeddings will need to be recomputed
   - Run a migration task to re-embed all documents:
     ```python
     from canopyresearch.tasks import task_batch_process_workspace
     task_batch_process_workspace.enqueue(workspace_id=your_workspace_id)
     ```

2. **Storage Impact:** Embeddings will use ~2x more storage space
   - 384 dimensions → 768 dimensions
   - Plan for increased database storage

3. **Performance Impact:** Expect ~5x slower embedding computation
   - Batch processing will take longer
   - Consider running during off-peak hours

4. **Quality Improvement:** You should see:
   - Better cluster separation
   - More accurate similarity scores
   - Improved alignment and novelty detection

### Keeping Existing Embeddings

If you want to keep using `all-MiniLM-L6-v2`:

```bash
export EMBEDDING_MODEL="all-MiniLM-L6-v2"
```

No migration needed - existing embeddings will continue to work.

## Model Selection Decision Tree

```
Do you prioritize quality over speed?
├─ Yes → Use all-mpnet-base-v2 (default)
└─ No → Continue
    │
    Do you have limited resources (CPU/memory)?
    ├─ Yes → Use all-MiniLM-L6-v2
    └─ No → Continue
        │
        Do you need better quality than L6-v2 but faster than mpnet?
        ├─ Yes → Use all-MiniLM-L12-v2
        └─ No → Use all-mpnet-base-v2 (default)
```

## Testing Different Models

To test model performance on your specific data:

1. **Create a test workspace** with sample documents
2. **Process documents** with different models
3. **Compare clustering results:**
   - Cluster quality and separation
   - Alignment scores
   - Novelty detection accuracy
4. **Measure performance:**
   - Embedding computation time
   - Memory usage
   - Overall system throughput

## Additional Resources

- [Sentence Transformers Documentation](https://www.sbert.net/)
- [MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard)
- [Model Hub](https://huggingface.co/models?library=sentence-transformers)
- [Model Comparison Guide](https://www.sbert.net/docs/pretrained_models.html)

## Support

For questions about model selection or performance issues, refer to:
- The [Sentence Transformers documentation](https://www.sbert.net/)
- The [MTEB benchmark results](https://huggingface.co/spaces/mteb/leaderboard)
- Your deployment's performance monitoring and logs
