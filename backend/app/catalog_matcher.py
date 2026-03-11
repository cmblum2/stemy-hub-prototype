import numpy as np
from openai import OpenAI

client = OpenAI()

def cosine(a, b):
    return np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b))

class CatalogMatcher:

    def __init__(self,catalog):
        self.catalog = catalog
        self.embeddings=[]
        self.build()

    def build(self):

        texts=[f"{v.get('id')} {v.get('label')} {v.get('description')}" for v in self.catalog]

        res=client.embeddings.create(
            model="text-embedding-3-small",
            input=texts
        )

        self.embeddings=[e.embedding for e in res.data]

    def match(self,phrase):

        emb=client.embeddings.create(
            model="text-embedding-3-small",
            input=[phrase]
        ).data[0].embedding

        scores=[cosine(emb,e) for e in self.embeddings]

        idx=int(np.argmax(scores))

        return self.catalog[idx]["id"], float(scores[idx])