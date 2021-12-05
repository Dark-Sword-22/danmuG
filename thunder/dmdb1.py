import uuid

print(type(uuid.uuid1()))

with open('dmdb1.py','r') as f:
    c = f.readlines()
print(c)