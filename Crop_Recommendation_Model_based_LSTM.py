"""라이브러리 호출"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
import copy
import os

from sklearn.preprocessing import StandardScaler
from sklearn.preprocessing import MinMaxScaler

"""데이터 로드"""

path_data = os.getcwd()+"/dataset_directory"
climate_andong = pd.read_csv(path_data+"/Climate_Andong.csv")
climate_andong = climate_andong.iloc[:,1:]
climate_chuncheon = pd.read_csv(path_data+"/Climate_Chuncheon.csv")
climate_chuncheon = climate_chuncheon.iloc[:,1:]
climate_jeju = pd.read_csv(path_data+"/Climate_Jeju.csv")
climate_jeju = climate_jeju.iloc[:,1:]

"""데이터 결측치 보간(스플라인)"""

climate_chuncheon.interpolate(method='spline', inplace=True, order=1)
climate_andong.interpolate(method='spline', inplace=True, order=1)
climate_jeju.interpolate(method='spline', inplace=True, order=1)

"""넘파이 배열화 및 스케일링 (전처리)"""

climate_chuncheon_np = climate_chuncheon.to_numpy()
climate_andong_np = climate_andong.to_numpy()
climate_jeju_np = climate_jeju.to_numpy()

climate_np = np.array([climate_chuncheon_np, climate_andong_np, climate_jeju_np])

"""GPU Setting"""

device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
print(torch.cuda.is_available())
print(device)

"""기후 데이터 넘파이 배열에 적재"""

climate = list()
for j in range(3) : # 0 chuncheon 1 andong 2 jeju
    s = 0
    climate_year = list()
    for i in range(10) :
        climate_year.append(climate_np[j, s:s+365, :])
        if i != 1 and 5 and 9 :
            s += 365
        else :
            s += 366
    climate_year = np.stack(climate_year, 0)
    climate.append(climate_year)
climate = np.stack(climate, 0)
climate.shape

"""훈련 데이터 셋 / 테스트 데이터 셋 분류"""

from torch.utils.data import TensorDataset
from torch.utils.data import DataLoader

x_ss = StandardScaler()

dataset_list = []

for i in range(3) :
    cc = climate[i] # (10, 365, 14)
    dataset_list_pos = []
    for j in range(14) :
        x_cc = np.delete(cc, j, axis=2).reshape(-1, 13)
        y_cc = cc[:,:,j]
        x_scaled = x_ss.fit_transform(x_cc)
        x_scaled = x_scaled.reshape(10, 365, 13)
        x_cc_train = torch.FloatTensor(x_scaled[:9, :,:])
        x_cc_test = torch.FloatTensor(x_scaled[9, :, :])
        y_cc_train = torch.FloatTensor(y_cc[:9, :])
        y_cc_test = torch.FloatTensor(y_cc[9, :])
        train_dataset = TensorDataset(x_cc_train, y_cc_train)
        train_loader = DataLoader(train_dataset, batch_size=365, shuffle=False)
        test_dataset = TensorDataset(x_cc_test, y_cc_test)
        test_loader = DataLoader(test_dataset, batch_size=365, shuffle=False)
        dataset = (train_loader, test_loader)
        dataset_list_pos.append(dataset)
    dataset_list.append(dataset_list_pos)

"""기후 데이터 예측 LSTM 모델"""

class Climate_LSTM(nn.Module):
    def __init__(self, input_dim, seq_len, n_layers, hidden_dim, output_dim, device):
        super(Climate_LSTM, self).__init__()
        self.n_layers = n_layers
        self.hidden_dim = hidden_dim
        self.device = device
        self.seq_len = seq_len
        self.output_dim = output_dim
        self.input_dim = input_dim
        
        self.lstm = nn.LSTM(self.input_dim, self.hidden_dim,
                            num_layers=self.n_layers,
                            batch_first=True)
        self.out = nn.Linear(self.hidden_dim, self.output_dim, bias=True)

    def forward(self, x): # 365*13
        h_0 = self._init_state()
        x, _ = self.lstm(x, h_0) # 365 * 100 
        h_t = x[:, -1] # 1 * 100
        logit = self.out(h_t)
        return logit

    def _init_state(self):
        new_cell_state = torch.zeros(self.n_layers, self.seq_len, self.hidden_dim).to(self.device)
        new_hidden_state = torch.zeros(self.n_layers, self.seq_len, self.hidden_dim).to(self.device)
        self.hidden = (new_hidden_state, new_cell_state)

"""훈련 및 평가 함수"""

def train(model, criterion, optimizer, data_loader):
    model.train()
    running_loss = 0
    for i, (x, y) in enumerate(data_loader):
        x, y = x.to(device), y.to(device)
      
        optimizer.zero_grad()
        logit = model(x)
        loss = criterion(logit, y)
        loss.backward()
        optimizer.step()

        running_loss += loss.item() * x.size(0)
        train_loss = running_loss / len(data_loader.dataset)
      
    return train_loss

def evaluate(model, criterion, data_loader):
    model.eval()
    running_loss = 0
    
    for i, (x, y) in enumerate(data_loader):
        x, y = x.to(device), y.to(device)
        
        logit = model(torch.unsqueeze(x, 0))
        predicted = torch.flatten(logit)
        loss = criterion(logit, y)
        running_loss += loss.item() * x.size(0)
        test_loss = running_loss / len(data_loader.dataset)
        
    return test_loss, predicted

def evaluate2(model, criterion, data_loader):
    model.eval()
    running_loss = 0
    
    for i, (x, y) in enumerate(data_loader):
        x, y = x.to(device), y.to(device)
        
        logit = model(x)
        predicted = torch.flatten(logit)
        loss = criterion(logit, y)
        running_loss += loss.item() * x.size(0)
        test_loss = running_loss / len(data_loader.dataset)
        
    return test_loss, predicted

"""LSTM 모델 파라미터 세팅"""

n_layers = 1
hidden_dim = 100
seq_len = 365
input_dim = 13
output_dim = 365
num_epochs = 1000
early_stop_patience = 100

"""훈련 및 평가 함수"""

def train_and_eval(model, train_loader, test_loader, epoch, criterion, optimizer, early_stop_patience) :
  train_loss_list = []
  test_loss_list = []
  best_model_wts = copy.deepcopy(model.state_dict())
  best_loss = None
  patience = 0

  for e in range(1, epoch+1):
      train_loss = train(model, criterion, optimizer, train_loader)
      test_loss, predicted = evaluate(model, criterion, test_loader)
      if e%10 == 0 :
          print("[Epoch: %d] train loss : %5.2f | test loss : %5.2f" % (e, train_loss, test_loss))
      train_loss_list.append(train_loss)
      test_loss_list.append(test_loss)
      if e == 1:
        best_loss = test_loss
      if test_loss <= best_loss :
        best_loss = test_loss
        patience = 0
        best_model_wts = copy.deepcopy(model.state_dict())
      else :
        patience += 1
      if (patience >= early_stop_patience) :     
              print('\nEarly Stopping')
              print(f'Epoch : {e}')
              break

  plt.subplot(1, 2, 1)
  plt.plot(np.arange(e), train_loss_list, label='train')
  plt.plot(np.arange(e), test_loss_list, label='test')
  plt.legend()
  plt.title("loss")

  for x, y in test_loader :
    y_test = y
  predicted = predicted.detach().cpu().numpy()
  
  predicted = predicted.reshape(-1,1)

  plt.subplot(1, 2, 2)
  plt.plot(np.arange(365), predicted, label = 'pred')
  plt.plot(np.arange(365), y_test, label = 'true')
  plt.legend()
  plt.title("predict")
  plt.show()
  return model

def train_again(model, criterion, optimizer, data_loader):
    model.train()
    running_loss = 0
    for i, (x, y) in enumerate(data_loader):
        x, y = x.to(device), y.to(device)
        
        model._init_state()
        optimizer.zero_grad()
        logit = model(torch.unsqueeze(x, 0))
        loss = criterion(logit, torch.unsqueeze(y,0))
        loss.backward()
        optimizer.step()

        running_loss += loss.item() * x.size(0)
        train_loss = running_loss / len(data_loader.dataset)
    return model

"""feature list"""

pos_list = ["춘천", "안동", "제주"]
feature_list = list(climate_andong.columns)

"""모델 훈련 및 평가 진행 후 해당 모델로 기후 데이터 예측"""

pred_list = []
for i in range(3) :
    pred_list_pos = list()
    for j in range(14):
        model = Climate_LSTM(input_dim, seq_len, n_layers, hidden_dim, output_dim, device).to(device)
        criterion = nn.MSELoss().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        print(f"\n{pos_list[i]}, {feature_list[j]}\n")
        trained_model = train_and_eval(model, dataset_list[i][j][0], dataset_list[i][j][1], num_epochs, criterion, optimizer, early_stop_patience)
        criterion = nn.MSELoss().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        trained_model = train_again(trained_model, criterion, optimizer, dataset_list[i][j][1])
        pred_x_list = []
        for k, (x, y) in enumerate(dataset_list[i][j][1]) :
            pred_x_list.append(x)
        logit = model(torch.unsqueeze(torch.FloatTensor(x).to(device), 0)) #
        predicted = torch.flatten(logit)
        plt.plot(np.arange(predicted.shape[0]), predicted.detach().cpu().numpy())
        plt.show()
        pred_list_pos.append(predicted)
    pred_list_pos = torch.stack(pred_list_pos, 0)
    pred_list.append(pred_list_pos)
pred_list = torch.stack(pred_list, 0)
pred_list

"""농작물 생산량 LSTM 모델"""

class Crop_LSTM(nn.Module):
    def __init__(self, input_dim, seq_len, n_layers, hidden_dim, output_dim, device):
        super(Crop_LSTM, self).__init__()
        self.n_layers = n_layers
        self.hidden_dim = hidden_dim
        self.device = device
        self.seq_len = seq_len
        self.output_dim = output_dim
        self.input_dim = input_dim
        
        self.lstm = nn.LSTM(self.input_dim, self.hidden_dim,
                            num_layers=self.n_layers,
                            batch_first=True)
        self.out = nn.Linear(self.hidden_dim, self.output_dim, bias=True)

    def forward(self, x): # 365*13
        h_0 = self._init_state()
        x, _ = self.lstm(x, h_0) # 365 * 100 
        h_t = x[:, -1] # 1 * 100
        logit = self.out(h_t)
        return logit

    def _init_state(self):
        new_cell_state = torch.zeros(self.n_layers, self.seq_len, self.hidden_dim).to(self.device)
        new_hidden_state = torch.zeros(self.n_layers, self.seq_len, self.hidden_dim).to(self.device)
        self.hidden = (new_hidden_state, new_cell_state)

"""모델 하이퍼파라미터 세팅"""

n_layers = 1
hidden_dim = 7
seq_len = 365
input_dim = 14
output_dim = 1
num_epochs = 1000
early_stop_patience = 100

"""농작물 데이터 전처리"""

Chuncheon_Grain = pd.read_csv(path_data+"/Chuncheon_Grain.csv")
Chuncheon_Grain = Chuncheon_Grain.iloc[:,1:]
Chuncheon_Grain_np = Chuncheon_Grain.to_numpy()
Chuncheon_Fruit = pd.read_csv(path_data+"/Chuncheon_Fruit.csv")
Chuncheon_Fruit = Chuncheon_Fruit.iloc[:,1:]
Chuncheon_Fruit_np = Chuncheon_Fruit.to_numpy()
Andong_Grain = pd.read_csv(path_data+"/Andong_Grain.csv")
Andong_Grain = Andong_Grain.iloc[:,1:]
Andong_Grain_np = Andong_Grain.to_numpy()
Andong_Fruit = pd.read_csv(path_data+"/Andong_Fruit.csv")
Andong_Fruit = Andong_Fruit.iloc[:,1:]
Andong_Fruit_np = Andong_Fruit.to_numpy()
Jeju_Grain = pd.read_csv(path_data+"/Jeju_Grain.csv")
Jeju_Grain = Jeju_Grain.iloc[:,1:]
Jeju_Grain_np = Jeju_Grain.to_numpy()
Jeju_Fruit = pd.read_csv(path_data+"/Jeju_Fruit.csv")
Jeju_Fruit = Jeju_Fruit.iloc[:,1:]
Jeju_Fruit_np = Jeju_Fruit.to_numpy()
Grain = [Chuncheon_Grain_np, Andong_Grain_np, Jeju_Grain_np]
Fruit = [Chuncheon_Fruit_np, Andong_Fruit_np, Jeju_Fruit_np]

"""데이터 넘파이 배열로 적재"""

pred_list = pred_list.reshape(3, 1, 365, 14)
pred_list = pred_list.detach().cpu().numpy()
pred_list.shape

"""훈련 데이터 및 테스트 데이터 셋 분류"""

ss = StandardScaler()

climate_new = []
dataloader_list = []

for i in range(3) :
  climate_new_np = np.concatenate([climate[i], pred_list[i]], 0)
  x_scaled = ss.fit_transform(climate_new_np.reshape(-1, 14))
  x_scaled = x_scaled.reshape(11, 365, 14)
  climate_new.append(x_scaled)
  x_train = torch.FloatTensor(x_scaled[1:9, :, :])
  x_test = torch.FloatTensor(x_scaled[9, :, :].reshape(1,365,14))
  Grain_dataloader_list = []
  for j in range(5) : 
    y_scaled = ss.fit_transform(Grain[i][:,j].reshape(-1,1))
    y_train = torch.FloatTensor(y_scaled[:8])
    y_test = torch.FloatTensor(y_scaled[8])
    train_dataset = TensorDataset(x_train, y_train)
    train_loader = DataLoader(train_dataset, batch_size=365, shuffle=False)
    test_dataset = TensorDataset(x_test, y_test)
    test_loader = DataLoader(test_dataset, batch_size=365, shuffle=False)
    Grain_dataloader_list.append((train_loader, test_loader))
    
  Fruit_dataloader_list= []
  for j in range(10) :
    y_scaled = ss.fit_transform(Fruit[i][:,j].reshape(-1,1))
    y_train = torch.FloatTensor(y_scaled[:8])
    y_test = torch.FloatTensor(y_scaled[8])
    train_dataset = TensorDataset(x_train, y_train)
    train_loader = DataLoader(train_dataset, batch_size=365, shuffle=False)
    test_dataset = TensorDataset(x_test, y_test)
    test_loader = DataLoader(test_dataset, batch_size=365, shuffle=False)
    Fruit_dataloader_list.append((train_loader, test_loader))

  dataloader_list.append((Grain_dataloader_list, Fruit_dataloader_list))

"""훈련 및 평가 함수"""

def train_and_eval2(model, train_loader, test_loader, epoch, criterion, optimizer, early_stop_patience) :
  train_loss_list = []
  test_loss_list = []
  best_model_wts = copy.deepcopy(model.state_dict())
  best_loss = None
  patience = 0

  for e in range(1, epoch+1):
      train_loss = train(model, criterion, optimizer, train_loader)
      test_loss, predicted = evaluate2(model, criterion, test_loader)
      if e%10 == 0 :
          print("[Epoch: %d] train loss : %5.2f | test loss : %5.2f" % (e, train_loss, test_loss))
      train_loss_list.append(train_loss)
      test_loss_list.append(test_loss)
      if e == 1:
        best_loss = test_loss
      if test_loss <= best_loss :
        best_loss = test_loss
        patience = 0
        best_model_wts = copy.deepcopy(model.state_dict())
      else :
        patience += 1
      if (patience >= early_stop_patience) :     
              print('\nEarly Stopping')
              print(f'Epoch : {e}')
              break

  plt.subplot(1, 2, 1)
  plt.plot(np.arange(e), train_loss_list, label='train')
  plt.plot(np.arange(e), test_loss_list, label='test')
  plt.legend()
  plt.title("loss")
  plt.show()

  for x, y in test_loader :
    y_test = y
  predicted = predicted.detach().cpu().numpy()
  
  predicted = predicted.reshape(-1,1)

  print(f"pred : {predicted.item()}, true : {y_test.item()}")
  return model

def train_again2(model, criterion, optimizer, data_loader):
    model.train()
    running_loss = 0
    for i, (x, y) in enumerate(data_loader):
        x, y = x.to(device), y.to(device)
        
        model._init_state()
        optimizer.zero_grad()
        logit = model(x)
        loss = criterion(logit, torch.unsqueeze(y,0))
        loss.backward()
        optimizer.step()

        running_loss += loss.item() * x.size(0)
        train_loss = running_loss / len(data_loader.dataset)
    return model

"""feature list"""

feature1 = list(Chuncheon_Grain.columns)
feature2 = list(Chuncheon_Fruit.columns)

"""모델 훈련 및 평가 진행 후 해당 모델로 농작물 생산량 예측"""

pred_list = []
for i in range(3) :
    pred_list_Grain = []
    pred_list_Fruit = []
    for j in range(5):
        model = Crop_LSTM(input_dim, seq_len, n_layers, hidden_dim, output_dim, device).to(device)
        criterion = nn.MSELoss().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        print(f"\n{pos_list[i]}, {feature1[j]}\n")
        trained_model = train_and_eval2(model, dataloader_list[i][0][j][0], dataloader_list[i][0][j][1], 
                                       num_epochs, criterion, optimizer, early_stop_patience)
        criterion = nn.MSELoss().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        trained_model = train_again2(trained_model, criterion, optimizer, dataloader_list[i][0][j][1])
        pred_x_list = []
        for k, (x, y) in enumerate(dataloader_list[i][0][j][1]) :
            pred_x_list.append(x)
        logit = trained_model(torch.FloatTensor(x).to(device)) #
        predicted = torch.flatten(logit)
        print(f"\npredicted : {predicted.item()}")
        pred_list_Grain.append(predicted.item())
    for j in range(10):
        model = Crop_LSTM(input_dim, seq_len, n_layers, hidden_dim, output_dim, device).to(device)
        criterion = nn.MSELoss().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        print(f"\n{pos_list[i]}, {feature2[j]}\n")
        trained_model = train_and_eval2(model, dataloader_list[i][1][j][0], dataloader_list[i][1][j][1], 
                                       num_epochs, criterion, optimizer, early_stop_patience)
        criterion = nn.MSELoss().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        trained_model = train_again2(trained_model, criterion, optimizer, dataloader_list[i][1][j][1])
        pred_x_list = []
        for k, (x, y) in enumerate(dataloader_list[i][1][j][1]) :
            pred_x_list.append(x)
        logit = trained_model(torch.FloatTensor(x).to(device)) #
        predicted = torch.flatten(logit)
        print(f"\npredicted : {predicted.item()}")
        pred_list_Fruit.append(predicted.item())
    pred_list.append((pred_list_Grain, pred_list_Fruit))

"""곡물 생산량 예측 표 출력"""

Grain_list = []
for i in range(3) :
  Grain_list.append(pred_list[i][0])
Grain_table = pd.DataFrame(np.array(Grain_list), columns=feature1, index=["춘천", "안동", "제주"])
Grain_table

"""각 지역에서 가장 생산량이 많을 것으로 추정되는 작물을 추천"""

Grain_table.idxmax(axis=1)

"""과채류 생산량 예측 표 출력"""

Fruit_list = []
for i in range(3) :
  Fruit_list.append(pred_list[i][1])
Fruit_table = pd.DataFrame(np.array(Fruit_list), columns=feature2, index=["춘천", "안동", "제주"])
Fruit_table

Fruit_table.idxmax(axis=1)
