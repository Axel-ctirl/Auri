# Retrieval

Retrieval is how Bread answers questions about code and documents the model was
never trained on. It embeds your files, finds the chunks nearest your question,
and puts them in the prompt with instructions to cite them.

It is the right tool for *facts*: your API surface, your config format, your
project's conventions. Fine-tuning is the right tool for *style*. Using the
wrong one for either is the most common mistake here.

## Knowledge spaces

Each space is its own vector index. Keeping your Paper documentation apart from
your school notes means a question about one does not retrieve the other, and
deleting a space deletes everything in it.

Spaces worth having:

```
Minecraft Paper Docs     Roblox Luau Docs        School Notes
Minecraft Fabric Docs    Discord Bot Project     Bread Source Code
Personal Plugin Projects
```

Create them on the Knowledge Spaces page or with
`POST /api/knowledge-spaces`.

## Supported files

```
.txt .md .json .csv .py .java .js .jsx .ts .tsx .lua .luau .go .rs
.c .h .cpp .hpp .cs .php .rb .sql .sh .html .css .yaml .yml .pdf
```

Anything else is refused with a message naming the supported list. PDFs need
`pypdf`, which is in `requirements.txt`.

## How indexing works

1. **Upload.** The file is written under `data/uploads/` with a name rebuilt from
   a sanitised basename. A name like `../../.ssh/authorized_keys` cannot escape
   that directory, and containment is checked rather than assumed.
2. **Hash.** A SHA-256 of the content. Re-uploading identical content is skipped
   with an explanation, and re-indexing an unchanged file is a no-op.
3. **Read.** Text files are decoded with a UTF-8 first, latin-1 fallback ladder.
   PDFs go through `pypdf` with page markers. Source code is read as data; Bread
   never imports or executes an uploaded file.
4. **Chunk.** Cut on line boundaries at roughly `chunk_size` characters with
   `chunk_overlap` characters repeated between neighbours. In source files the
   cut is pulled back to the nearest definition boundary, so a function's
   signature stays attached to its body.
5. **Embed.** Each chunk becomes a vector.
6. **Store.** Vectors go to the space's index, chunks and metadata to SQLite.

Re-indexing deletes a document's old vectors first, so it is a replace and not
an append.

## Embeddings

By default Bread uses `sentence-transformers/all-MiniLM-L6-v2` when
`sentence-transformers` is installed and the model is cached, and falls back to a
built-in hashing encoder when it is not.

The fallback hashes word and character n-grams into a fixed-width vector. It
works offline with no downloads, and it is clearly weaker: it matches shared
vocabulary rather than shared meaning. A search for "how do I stop a player
moving" will find a chunk containing those words and will not find one about
`setWalkSpeed`.

Bread always reports which encoder produced an index, so you are never guessing
which one you are on. To get the real one:

```bash
pip install sentence-transformers
python scripts/download_model.py \
  --model-id sentence-transformers/all-MiniLM-L6-v2 --accept-download --embedding
```

Then re-index each space from the Documents page. Switching embedding models
invalidates existing vectors; Bread refuses to mix dimensions rather than
returning nonsense.

## Tuning

| Setting | Default | What moving it does |
| --- | --- | --- |
| `RAG_CHUNK_SIZE` | 900 | Larger chunks carry more context and match less precisely |
| `RAG_CHUNK_OVERLAP` | 150 | More overlap means fewer answers cut in half, and a larger index |
| `RAG_TOP_K` | 5 | More chunks fill the context window and dilute the question |
| `RAG_RERANK_ENABLED` | false | A cross-encoder rescores candidates: more accurate, slower |

Chunk settings apply per space and only affect documents indexed afterwards.
Re-index a space to apply a change to what is already in it.

Reranking fetches four times `top_k` candidates and rescores them with a
cross-encoder. If the reranker model is not cached, Bread skips it and says so
rather than failing.

## Citations

Every retrieved chunk is labelled `[1]`, `[2]` and so on in the prompt, and the
system prompt instructs the model to cite them and to say when the context does
not answer the question. The interface shows the filename, chunk number, line
range and similarity score under each answer.

A model can still ignore that instruction. Smaller models ignore it more often.
Check the cited chunk when an answer matters.

## Vector storage

The default store is a NumPy matrix per space under `data/vectors/<space_id>/`.
No server, no daemon, no network listener. It handles a personal index of a few
hundred thousand chunks comfortably: a search is one matrix multiply.

For larger collections, `VECTOR_BACKEND=chroma` swaps in ChromaDB's persistent
client (`pip install chromadb`).

## Testing retrieval

The Documents page has a search box that shows exactly what would be retrieved
for a question, with scores. Use it before blaming the model: if the right chunk
is not in the results, the problem is the index, not the answer.

```bash
curl -X POST http://127.0.0.1:8000/api/rag/search \
  -H "Content-Type: application/json" \
  -d '{"query": "how do I cancel a block break event", "top_k": 5}'
```

## Privacy

Documents are read, chunked, embedded and stored locally. Nothing is uploaded.
The embedding model runs on your machine. Deleting a document removes its
database rows, its vectors and the uploaded file itself.
