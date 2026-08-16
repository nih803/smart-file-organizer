import os

folder = "test_folder"
files = os.listdir(folder)

for i in files:
    name, extension = os.path.splitext(i)
    print(name, extension)