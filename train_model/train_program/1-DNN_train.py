import torch
from datasets import load_from_disk
from transformers import BertTokenizer
from datasets import load_dataset
#定义数据集
class Dataset(torch.utils.data.Dataset):
    def __init__(self,str):
        self.dataset = load_from_disk('../data/ChnSentiCorp')[str]

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, i):
        text = self.dataset[i]['text']
        label = self.dataset[i]['label']

        return text, label
dataset = Dataset('train')

print(dataset[0])

#加载字典和分词工具
token = BertTokenizer.from_pretrained('bert-base-chinese')      #加载预分词器
print(token)
def collate_fn(data):
    sents = [i[0] for i in data]
    labels = [i[1] for i in data]

    #编码---使用自带的批量成对编码
    data = token.batch_encode_plus(batch_text_or_text_pairs=sents,      #传递数据的格式有所变化
                                   truncation=True,         #达到最大长度后截断
                                   #达到最大长度后截断
                                   padding='max_length',
                                   max_length=500,
                                   #返回pytorch类型，默认是返回list
                                   return_tensors='pt',
                                   #返回length，标识长度
                                   return_length=True)
    #将分词后的结果取出来
    #input_ids:编码之后的数字
    #attention_mask:是补零的位置是0,其他位置是1
    input_ids = data['input_ids']
    attention_mask = data['attention_mask']
    token_type_ids = data['token_type_ids']
    labels = torch.LongTensor(labels)

    #print(data['length'], data['length'].max())

    return input_ids, attention_mask, token_type_ids, labels


#数据加载器
loader = torch.utils.data.DataLoader(dataset=dataset,
                                     batch_size=32,     #决定与训练模型的单次训练句子，越大则计算出来的准确率就越平稳
                                     collate_fn=collate_fn,
                                     shuffle=True,
                                     drop_last=True)

for i, (input_ids, attention_mask, token_type_ids,labels) in enumerate(loader):
    break

print(len(loader))      #批处理大小batch_size*loder的大小等于训练集train的长度
from transformers import BertModel

#加载预训练模型
pretrained = BertModel.from_pretrained('bert-base-chinese')     #通过name加载网络上的与训练模型，并且缓存到cache中

#不训练,不需要计算梯度：不会修改预训练模型的参数，只训练下游任务模型
for param in pretrained.parameters():
    param.requires_grad_(False)

#模型试算
out = pretrained(input_ids=input_ids,
           attention_mask=attention_mask,
           token_type_ids=token_type_ids)   #将tokenizer分词器得到的结果参数直接喂给预训练模型
print(out.last_hidden_state.shape)          #输出最后一个隐藏层的参数类型 --torch.Size(16,500,768)   16:batchSize,每一批训练16个句子，500是句子长度（多则截断，短则补长），768是词编码的维度，即每个词编码成768维度的向量

#使用bert抽取特征，然后再做下游任务的迁移学习
#定义下游任务模型
class Model(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.fc = torch.nn.Linear(768, 2)       #只包括一个全连接的神经网络，输入是与训练模型的768维度向量，输出是二
    def forward(self, input_ids, attention_mask, token_type_ids):
        with torch.no_grad():       #该方法表示当前计算不需要反向传播
            out = pretrained(input_ids=input_ids,
                       attention_mask=attention_mask,
                       token_type_ids=token_type_ids)
        out = self.fc(out.last_hidden_state[:, 0])      #将预训练模型抽取数据中的特征（情感分类只取第0个词的特征）交给全连接层计算
        out = out.softmax(dim=1)        #指定第1个维度的和为1
        return out          #torch(32,1)


model = Model()
model.load_state_dict(torch.load('./model/model_new.pth'))
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model.to(device)

print(model(input_ids=input_ids,
      attention_mask=attention_mask,
      token_type_ids=token_type_ids).shape)

from transformers import AdamW

#训练
optimizer = AdamW(model.parameters(), lr=5e-4)
criterion = torch.nn.CrossEntropyLoss()     #计算以下损失，反向更新

model.train()
for i, (input_ids, attention_mask, token_type_ids,
        labels) in enumerate(loader):       #loader一共有300层，将tokenizer的分词结果输出给预训练模型
    out = model(input_ids=input_ids,
                attention_mask=attention_mask,
                token_type_ids=token_type_ids)      #本质上就是调用forward方法

    loss = criterion(out, labels)       #计算出损失率
    loss.backward()                     #通过损失率反向传播
    optimizer.step()
    optimizer.zero_grad()

    if i % 5 == 0:
        out = out.argmax(dim=1)
        accuracy = (out == labels).sum().item() / len(labels)

        print("第"+str(i)+"轮  ", "损失率是"+str(loss.item()), "准确率是"+str(accuracy))
    if i % 100 == 0:
        torch.save(model.state_dict(), './model/model_new.pth')
        print("保存成功！")
    if i == 300:
        break

torch.save(model.state_dict(),'./model/model_new.pth')
print("保存成功！")


# modeltest = Model()
# modeltest.load_state_dict(torch.load('./model/modelpara.pth'))
# #测试
# def test():
#     modeltest.eval()
#     correct = 0
#     total = 0
#
#     loader_test = torch.utils.data.DataLoader(dataset=Dataset('validation'),
#                                               batch_size=32,
#                                               collate_fn=collate_fn,
#                                               shuffle=True,
#                                               drop_last=True)
#
#     for i, (input_ids, attention_mask, token_type_ids,
#             labels) in enumerate(loader_test):
#
#         if i == 5:
#             break
#
#         print(i)
#
#         with torch.no_grad():
#             out = model(input_ids=input_ids,
#                         attention_mask=attention_mask,
#                         token_type_ids=token_type_ids)
#
#         out = out.argmax(dim=1)
#         correct += (out == labels).sum().item()
#         total += len(labels)
#
#     print(correct / total)
# test()
