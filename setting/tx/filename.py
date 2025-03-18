import os

# 获取当前目录下所有.json文件
json_files1 = [file for file in os.listdir("setting/tx/c1") if file.endswith('.json')]
json_files2 = [file for file in os.listdir("setting/tx/c2") if file.endswith('.json')]
json_files3 = [file for file in os.listdir("setting/tx/c3") if file.endswith('.json')]
# 将文件名写入txt文档
with open('setting/tx/c1/filelist.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(json_files1))
with open('setting/tx/c2/filelist.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(json_files2))
with open('setting/tx/c3/filelist.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(json_files3))
print(f"已找到 {len(json_files1)} 个JSON文件，并保存到 'setting/tx/c1/filelist.txt")
print(f"已找到 {len(json_files2)} 个JSON文件，并保存到 'setting/tx/c2/filelist.txt")
print(f"已找到 {len(json_files3)} 个JSON文件，并保存到 'setting/tx/c3/filelist.txt")