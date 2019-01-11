
# coding: utf-8

# # Class for meteorological data handling
# Developing processes of classes aiming to create ther class files to be invoked.<br>
# （財）気象業務支援センター「気象データベース」の図化解析用に開発しているが，pandas DataFrameを活用することで，Classの汎用化を目指す．<br>
# 現在のところ，「地上観測」のみに対応している．「アメダス」は今後対応する予定である．<br>
# 1991年以降は毎時データで全天日射量あり（一部観測所のみ），1990年以前は3時間データで全天日射量，日照時間，降水量がない
# #### Author: Jun Sasaki, Coded on Sep. 9, 2017, Revised on June 17, 2018
# ## 課題： 1990年以前の3時間データと全天日射量対応，アメダスデータ対応
# 1990年以前と1991年以降を同時に読み込むことは可能だが，時間間隔が異なる．任意の時間間隔にリサンプリングできるようにする．<br>
# 全天日射や欠損値への対応を検討する．<br>
# RMKが2の場合は0の値が入っているようであるが，このままでよいか要検討．全天日射では2は夜間に相当するので，0とするのでよい．

# In[ ]:


import sys
#import os
import glob
import numpy as np
import math
import pandas as pd
import datetime
import subprocess
from pandas.tseries.offsets import Hour
from dateutil.parser import parse
#import json  # json cannot manipulate datetime
from matplotlib import pyplot as plt
from matplotlib.ticker import MultipleLocator, FormatStrFormatter
from matplotlib.dates import date2num, YearLocator, MonthLocator, DayLocator, DateFormatter

get_ipython().run_line_magic('matplotlib', 'inline')


# In[ ]:


class Met:
    '''気象データベース・地上観測DVD，アメダスDVDの時系列データ抽出
  +--------+------------------------------------------------------------+
  |リマーク|            解                                  説          |
  +--------+------------------------------------------------------------+
  |   ０   |観測値が未作成の場合                                        |
  +--------+------------------------------------------------------------+
  |   １   |欠測                                                        |
  +--------+------------------------------------------------------------+
  |   ２   |観測していない場合                                          |
  +--------+------------------------------------------------------------+
  |   ３   |日の極値が真の値以下の場合，該当現象がない推定値の場合      |
  +--------+------------------------------------------------------------+
  |   ４   |日の極値が真の値以上の場合，該当現象がない地域気象観測データ|
  |        |を使用する場合                                              |
  +--------+------------------------------------------------------------+
  |   ５   |推定値が含まれる場合，または２４回平均値で欠測を含む場合    |
  +--------+------------------------------------------------------------+
  |   ６   |該当する現象がない場合（降水量，日照時間，降雪，積雪，最低海|
  |        |面気圧）                                                    |
  +--------+------------------------------------------------------------+
　|   ７ 　|日の極値の起時が前日の場合　　　　　　　　　　　　　　　　　|
　+--------+------------------------------------------------------------+
　|   ８ 　|正常な観測値　　　　　　　　　　　　　　　　　　　　　　　　|
　+--------+------------------------------------------------------------+
  |   ９   |日の極値の起時が翌日の場合，または１９９０年までの８０型地上|
  |        |気象観測装置からの自動取得値                                |
  +--------+------------------------------------------------------------+
  '''
    rmk = {"0":"観測値が未作成の場合", "1": "欠測", "2":"観測していない場合",            "3":"日の極値が真の値以下の場合，該当現象がない推定値の場合",            "4":"日の極値が真の値以上の場合，該当現象がない地域気象観測データを使用する場合",            "5":"推定値が含まれる場合，または２４回平均値で欠測を含む場合",            "6":"該当する現象がない場合（降水量，日照時間，降雪，積雪，最低海面気圧）",            "7":"日の極値の起時が前日の場合", "8":"正常な観測値",            "9":"日の極値の起時が翌日の場合，または１９９０年までの８０型地上気象観測装置からの自動取得値"}
    nan_0_1_RMK = [0, 1, 2]
    def __init__(self, datetime_ini, datetime_end, stn, dir):
        self.datetime_ini = parse(datetime_ini)
        self.datetime_end = parse(datetime_end)
        print("Initial datetime = ", self.datetime_ini)
        print("End datetime = ", self.datetime_end)
        self.stn = stn
        self.dir = dir

    def set_missing_values(self, df, rmk_cols, rmk_nans):
        '''DataFrame dfを入力し，RMK列が欠損値条件を満たす行の一つ前の列の値をnp.nanに置換する'''
        ### rmk_cols = [col for col in df.columns if 'RMK' in col]  ### RMK列名のリスト
        for rmk_col in rmk_cols:
            for rmk_nan in rmk_nans:
                idx = df.columns.get_loc(rmk_col) - 1  ### RMKに対応する値の列インデックス
                df.iloc[:, idx].mask(df[rmk_col] == rmk_nan, np.nan, inplace=True)
        return df


# In[ ]:


class Met_GWO(Met):
    '''気象データベース・地上観測DVDの時別値（1990年以前は3時間間隔）データ抽出
       Directory name is suppoed to be stn + "/", file name supposed to be stn + year + ".csv"'''
    col_names_jp = ["観測所ID","観測所名","ID1","年","月","日","時",                     "現地気圧(0.1hPa)","ID2","海面気圧(0.1hPa)","ID3",                     "気温(0.1degC)","ID4","蒸気圧(0.1hPa)","ID5",                     "相対湿度(%)","ID6","風向(1(NNE)～16(N))","ID7","風速(0.1m/s)","ID8",                     "雲量(10分比)","ID9","現在天気","ID10","露天温度(0.1degC)","ID11",                     "日照時間(0.1時間)","ID12","全天日射量(0.01MJ/m2/h)","ID13",                     "降水量(0.1mm/h)","ID14"]
    col_names = ["KanID","Kname","KanID_1","YYYY","MM","DD","HH","lhpa","lhpaRMK",                  "shpa","shpaRMK","kion","kionRMK","stem","stemRMK","rhum","rhumRMK",                  "muki","mukiRMK","sped","spedRMK","clod","clodRMK","tnki","tnkiRMK",                  "humd","humdRMK","lght","lghtRMK","slht","slhtRMK","kous","kousRMK"]
    col_items_jp = ["現地気圧(hPa)","海面気圧(hPa)",                     "気温(degC)","蒸気圧(hPa)",                     "相対湿度(0-1)","風向(0-360)","風速(m/s)",                     "雲量(0-1)","現在天気","露天温度(degC)",                     "日照時間(時間)","全天日射量(W/m2)",                     "降水量(mm/h)","風速u(m/s)","風速v(m/s)"]
    col_items =  ["lhpa",                   "shpa","kion","stem","rhum",                   "muki","sped","clod","tnki",                   "humd","lght","slht","kous","u","v"]

    def __init__(self, datetime_ini = "2014-1-10 15:00:00", datetime_end = "2014-6-1 00:00:00",                  stn = "Tokyo", dir = "../../../met/GWO/"):
        super().__init__(datetime_ini, datetime_end, stn, dir)

        self.names_jp = Met_GWO.col_names_jp
        self.names = Met_GWO.col_names
        self.items_jp = Met_GWO.col_items_jp
        self.items = Met_GWO.col_items

        ### the values of rmk to be set as NaN (RMK=0, 1, 2)
        self.rmk_nan01 = ["0", "1"]  ### sghtとslhtの夜間はRMK=2なので，RMK=2を欠損値としない
        self.rmk_nan = ["0", "1", "2"]  ### clodとtnkiは3時間間隔で，観測なしのRMK=2を欠損値とする必要がある
        self.__df, self.__df_org, self.__df_interp, self.__df_interp_1H = self.__create_df()

    ### propertyの名称をcreate_dfでの名称から変更している．通常使うself.__df_interp_1Hをself.dfと簡単に呼べる様にするため
    @property
    def df(self):
        '''1時間間隔で欠損値を可能な限り補間したDataFrame'''
        return self.__df_interp_1H
    @property
    def df_org(self):
        '''元々の時間間隔で欠損値を可能な限り補間したDataFrame．1990年を境に時間間隔が異なる'''
        return self.__df_interp
    @property
    def df_na_rmk(self):
        '''元々の時間間隔で欠損値を含むDataFrame．df_naと同様だが，RMK値を欠損値にする'''
        return self.__df
    @property
    def df_na(self):
        '''元々の時間間隔で欠損値を含むDataFrame．df_na_rmkと同様だが変数値を欠損値にする'''
        return self.__df_org

    def to_csv(self, df, fo_path='./df.csv'):
        '''DataFrame dfをCSV出力するmethod
           引数 df: DataFrame（必須）, fo_path=出力先ファイルのpath'''
        df.to_csv(fo_path, encoding='utf-8', )  ### CSVで出力する．デフォルトではWindows版ではShiftJISとなるため，UTF-8を明示する．
        cmd = 'nkf -w -Lu --overwrite ' + fo_path  ### 改行コードをLinuxタイプのLFに変更しておく（Linuxとの互換性のため）
        subprocess.call(cmd)
    def read_csv(self, fi_path):
        '''fi_pathからCSV fileを読み込みDataFrameを作って返す
           引数 fi_path=CSV fileのpath  戻り値 DataFrame
        '''
        return pd.read_csv(fi_path, index_col=0, parse_dates=True)  ### 出力したCSVをDataFrameとして読み込む

    '''以下は隠避されたmethod．意味が分からなくても使うには困らない'''
    def __create_df(self):
        start = self.datetime_ini
        end   = self.datetime_end
        if start >= end:
            print("ERROR: start >= end")
            sys.exit()
        Ys, Ye = int(start.strftime("%Y")), int(end.strftime("%Y"))
        fdir = self.dir + self.stn + "/"  # data dir
        print("Data directory = ", fdir)
        fstart = glob.glob(fdir + self.stn + str(Ys-1) + ".csv") # check Ys-1 exists?
        if len(fstart) == 1:
            Ys += -1
        else:
            fstart = glob.glob(fdir + self.stn + str(Ys) + ".csv")
        if len(fstart) != 1:
            print(fstart)
            print('ERROR: fstart does not exist or has more than one file.')
            sys.exit()
        fend = glob.glob(fdir + self.stn + str(Ye+1) + ".csv")  # Ye+1 exists?
        if len(fend) == 1:
            Ye += 1
        else:
            fend = glob.glob(fdir + self.stn + str(Ye) + ".csv")
        if len(fend) != 1:
            print('fend= ', fend)
            print('ERROR: fend does not exist or has more than one file.')
            sys.exit()

        tsa = []  ### RMKの欠損値を考慮
        tsa_org = []  ### RMKの欠損値を考慮しない，オリジナルと同一
        fyears = list(range(Ys, Ye+1)) # from Ys to Ye

        ### Reading csv files
        ### カラム毎に欠損値を指定する
        ### 欠損値を考慮しないデータフレームも併せて作成する
        na_values =  {"lhpaRMK":self.rmk_nan,                       "shpaRMK":self.rmk_nan,"kionRMK":self.rmk_nan,"stemRMK":self.rmk_nan,"rhumRMK":self.rmk_nan,                       "mukiRMK":self.rmk_nan,"spedRMK":self.rmk_nan,"clodRMK":self.rmk_nan,"tnkiRMK":self.rmk_nan,                       "humdRMK":self.rmk_nan,"lghtRMK":self.rmk_nan01,"slhtRMK":self.rmk_nan01,"kousRMK":self.rmk_nan}
        for year in fyears:
            file = fdir + self.stn + str(year) + ".csv"
            print(file)
            tsa.append(pd.read_csv(file, header = None, names = self.names,                  parse_dates=[[3,4,5]], na_values = na_values))
            tsa_org.append(pd.read_csv(file, header = None, names = self.names,                  parse_dates=[[3,4,5]]))
            
        def create_df(tsa):
            '''Create df from tsa'''
            df = pd.concat(tsa)
            df.index = [x + y * Hour() for x,y in zip(df['YYYY_MM_DD'],df['HH'])]
            df.drop("YYYY_MM_DD", axis=1, inplace=True)
            df.drop("HH", axis=1, inplace=True)
            df=df[start:end]
            return df
        df = create_df(tsa)  ### 欠損値を考慮したDataFrame
        df_org = create_df(tsa_org)  ### 欠損値を無視した，元データと同じDataFrame

        ### Check missing values
        check_list=["lhpa","shpa","kion","stem","rhum","muki","sped","clod","tnki",                     "humd","lght","slht","kous"]
        for lst in check_list:
            rmk = lst + "RMK"
            mask = df[rmk] == 1 # 1:missing value
            missing = df[lst][mask]
        if len(missing)==0:
            #print("No missing values in", lst)
            pass
        else:
            print(missing, "in", lst)

        ### Unit conversions
        '''
        TEEM出力：海面気圧(hPa), 気温(degC)，蒸気圧(hPa)，相対湿度(0-1)，風速(m/s)，
                  風向(deg), 雲量(0-1), 全天日射量(W/m2), 降水量(m/h)
        '''
        def unit_conversion(df):
            df['lhpa']=df['lhpa']/1.0e1 # [0.1hPa] -> [hPa]
            df['shpa']=df['shpa']/1.0e1 # [0.1hPa] -> [hPa]
            df['kion']=df['kion']/1.0e1 # [0.1degC] -> [degC]
            df['stem']=df['stem']/1.0e1 # [0.1hPa] -> [hPa]
            df['rhum']=df['rhum']/1.0e2 # [%] -> [0-1]
            df['muki']=-90.0 - df['muki'] * 22.5 # [0-16] -> [deg]  0=NA, 1=NNE, .., 8=S, ..., 16=N
            df['muki']=df['muki'] % 360.0 # 0-360
            df['sped']=df['sped']/1.0e1 # [0.1m/s] -> [m/s]
            df['clod']=df['clod']/1.0e1 # [0-10] -> [0-1]
            df['humd']=df['humd']/1.0e1 # [0.1degC] -> [degC]
            df['lght']=df['lght']/1.0e1 # [0.1h] -> [h]
            df['slht']=df['slht']*1.0e4/3.6e3 # [0.01MJ/m2/h] -> [J/m2/s] = [W/m2]
            ### wind vector (u,v)
            rad = df["muki"].values * 2 * np.pi / 360.0
            (u, v) = df["sped"].values * (np.cos(rad), np.sin(rad))
            df["u"] = u
            df["v"] = v
        unit_conversion(df)
        unit_conversion(df_org)

        def df_interp(df, df_org):
            '''RMKをチェックして欠損値を見つけ，RMKは元の整数を保持したまま，値を欠損値にし，
               それを適切に補間したDataFrame df_interpを作る．
               さらに，df_interpをすべて1時間間隔にreindexし，欠損値を埋めたdf_interp_1Hを作る
            '''
            ### RMKがNaNである行rowsを抽出する Find rows containing NaN
            rows = pd.isnull(df).any(axis=1).nonzero()[0]
            ### RMKがNaNである列colsを見つける．次行のコメントはrow=280において，列を見つける方法を例として示す
            ### cols = pd.isnull(df0.iloc[280]).nonzero()[0]  ### in case of row =280
            ### すべてのrowsについてRMKがNaNである列を見つけ，該当する行と列の番号を持つリストnan_ar[rows][cols]を作る
            ### nan_ar[0][0]は一つ目の行（0）の行番号，nan_ar[0][1]はその行の列番号を含むarrayを返す．
            ###   一般に一つの行には複数のNaNが含まれるので，列番号はarrayになる
            ### すべての行についてリスト内包を用い，リストnan_arを作る．ただし，列番号-1とすることで，RMKのデータ値の列番号とする．
            nan_ar=[[row, pd.isnull(df.iloc[row]).nonzero()[0]-1] for row in rows]
            ### print(nan_ar)
            na_rows=[nan_ar[row][0] for row in range(len(rows))]  ### rows containing NaN
            ### print(na_rows)
            df_interp=df_org
            for row in range(len(nan_ar)):
                df_interp.iloc[nan_ar[row][0],nan_ar[row][1]]=np.nan
            ### 欠損値を内挿したdf_interpを作る
            df_interp.interpolate(method='time', inplace=True)

            ### 1990年以前の3時間間隔を1時間間隔にする
            ### 1時間間隔のインデックスを作る
            new_index = pd.date_range(self.datetime_ini, self.datetime_end, freq='1H')
            ### ffillを適用するカラム名のリスト
            cols_ffill=['KanID', 'Kname', 'KanID_1', 'lhpaRMK', 'shpaRMK', 'kionRMK', 'stemRMK', 'rhumRMK', 'mukiRMK', 'spedRMK',                         'clodRMK', 'tnkiRMK', 'humdRMK', 'lghtRMK', 'slhtRMK', 'kousRMK']
            ### カラム全体のリストからffillを適用するカラムを削除するラムダ関数dellistを定義
            dellist = lambda items, sublist: [item for item in items if item not in sublist]
            ### 内挿を適用するカラム名のリストをつくる
            cols_interp=dellist(df_interp.columns, cols_ffill)
            ### print(cols_interp)
            ### 1時間間隔のインデックスを適用し，ffillを適用すべきカラムを対象に補完実行．結果をdf_ffillに入れる
            df_ffill = df_interp.reindex(new_index).loc[:, cols_ffill].fillna(method='ffill')
            ### カラムKname以外のカラムのdtypeをintに戻す（NaNを扱うとintだったものがfloatに変更されてしまう）
            df_ffill[dellist(df_ffill.columns, ['Kname'])] = df_ffill[dellist(df_ffill.columns, ['Kname'])].astype(int)
            ### 1時間間隔のインデックスを適用し，時間内挿すべきカラムを対象に内挿実行．結果をdf_interpに入れる
            df_interp_1H = df_interp.reindex(new_index).loc[:, cols_interp].interpolate(method='time')
            ### df_ffillとdf_interpを連結し，カラムの順序をdf1と同じとしたデータフレームdfを作る
            ### これで一応完成だが，1990年以前の全天日射量，日照時間，降水量への対応を今後進める
            df_interp_1H = pd.concat([df_ffill, df_interp_1H], axis=1)[df_interp.columns]
            return df_interp, df_interp_1H
        
        df_interp, df_interp_1H = df_interp(df, df_org)
        return df, df_org, df_interp, df_interp_1H

    #@staticmethod
    #def check_data():
    #    '''CSV気象データをチェックするための静的メソッド'''
    #    print(self.names_jp)


# # データチェック用のClass

# In[ ]:


class Met_GWO_check(Met_GWO):
    def __init__(self, datetime_ini = "2014-1-1 15:00:00", datetime_end = "2014-6-1 00:00:00",                  stn = "Tokyo", dir = "../GWO/Hourly/"):
        Met.__init__(self, datetime_ini, datetime_end, stn, dir)  ### Class Met_GWO inherits Class Met.
        self.names_jp = Met_GWO.col_names_jp
        self.names = Met_GWO.col_names
        self.items_jp = Met_GWO.col_items_jp
        self.items = Met_GWO.col_items

        ### the values of rmk to be set as NaN (RMK=0, 1, 2)
        self.rmk_nan01 = ["0", "1"]  ### sghtとslhtの夜間はRMK=2なので，RMK=2を欠損値としない
        self.rmk_nan = ["0", "1", "2"]  ### clodとtnkiは3時間間隔で，観測なしのRMK=2を欠損値とする必要がある
        self.__df_org = self.__create_df()
    @property
    def df_org(self):
        return self.__df_org

    def __create_df(self):  ### Met_GWO()の__create_df()の上部と同じなので，分割する等して使い回しできるよう修正する
        start = self.datetime_ini
        end   = self.datetime_end
        if start >= end:
            print("ERROR: start >= end")
            sys.exit()
        Ys, Ye = int(start.strftime("%Y")), int(end.strftime("%Y"))
        fdir = self.dir + self.stn + "/"  # data dir
        print("Data directory = ", fdir)
        fstart = glob.glob(fdir + self.stn + str(Ys-1) + ".csv") # check Ys-1 exists?
        if len(fstart) == 1:
            Ys += -1
        else:
            fstart = glob.glob(fdir + self.stn + str(Ys) + ".csv")
        if len(fstart) != 1:
            print(fstart)
            print('ERROR: fstart does not exist or has more than one file.')
            sys.exit()
        fend = glob.glob(fdir + self.stn + str(Ye+1) + ".csv")  # Ye+1 exists?
        if len(fend) == 1:
            Ye += 1
        else:
            fend = glob.glob(fdir + self.stn + str(Ye) + ".csv")
        if len(fend) != 1:
            print('fend= ', fend)
            print('ERROR: fend does not exist or has more than one file.')
            sys.exit()

        tsa = []  ### RMKの欠損値を考慮
        tsa_org = []  ### RMKの欠損値を考慮しない，オリジナルと同一
        fyears = list(range(Ys, Ye+1)) # from Ys to Ye

        ### Reading csv files
        ### カラム毎に欠損値を指定する
        ### 欠損値を考慮しないデータフレームも併せて作成する
        na_values =  {"lhpaRMK":self.rmk_nan,                       "shpaRMK":self.rmk_nan,"kionRMK":self.rmk_nan,"stemRMK":self.rmk_nan,"rhumRMK":self.rmk_nan,                       "mukiRMK":self.rmk_nan,"spedRMK":self.rmk_nan,"clodRMK":self.rmk_nan,"tnkiRMK":self.rmk_nan,                       "humdRMK":self.rmk_nan,"lghtRMK":self.rmk_nan01,"slhtRMK":self.rmk_nan01,"kousRMK":self.rmk_nan}
        for year in fyears:
            file = fdir + self.stn + str(year) + ".csv"
            print(file)
            tsa.append(pd.read_csv(file, header = None, names = self.names,                  parse_dates=[[3,4,5]], na_values = na_values))
            tsa_org.append(pd.read_csv(file, header = None, names = self.names,                  parse_dates=[[3,4,5]]))
            
        def create_df(tsa):
            '''Create df from tsa'''
            df = pd.concat(tsa)
            df.index = [x + y * Hour() for x,y in zip(df['YYYY_MM_DD'],df['HH'])]
            df.drop("YYYY_MM_DD", axis=1, inplace=True)
            df.drop("HH", axis=1, inplace=True)
            df=df[start:end]
            return df
        #df = create_df(tsa)  ### 欠損値を考慮したDataFrame
        df_org = create_df(tsa_org)  ### 欠損値を無視した，元データと同じDataFrame
        return df_org


class Met_GWO_daily(Met):
    '''気象データベース・地上観測DVDの日別値データ抽出
       全天日射量日別値の単位について：1961-1980は1cal/cm2，1981以降は0.1MJ/m2
       Directory name is suppoed to be stn + "/", file name supposed to be stn + year + ".csv"'''
    def __init__(self, datetime_ini = "2014-1-10 15:00:00", datetime_end = "2014-6-1 00:00:00",                  stn = "Tokyo", dir = "../../../met/GWO/Daily/"):
        super().__init__(datetime_ini, datetime_end, stn, dir)
        #super().__init__()
        self.names_jp = ["観測所ID","観測所名","ID1","年","月","日",                          "平均現地気圧(0.1hPa)","ID2","平均海面気圧(0.1hPa)","ID3", "最低海面気圧",                          "ID4", "平均気温(0.1degC)","ID5", "最高気温(0.1degC)","ID6", "最低気温(0.1degC)","ID7",                          "平均蒸気圧(0.1hPa)","ID8", "平均相対湿度(%)", "ID9", "最小相対湿度(%)", "ID10",                          "平均風速(0.1m/s)","ID11", "最大風速(0.1m/s)","ID12", "最大風速風向(1(NNE)～16(N))","ID13",                          "最大瞬間風速(0.1m/s)","ID14", "最大瞬間風向(1(NNE)～16(N))", "ID15",                          "平均雲量(0.1)","ID16", "日照時間(0.1時間)", "ID17", "全天日射量(0.1MJ/m2)", "ID18",                          "蒸発量(0.1mm)", "ID19", "日降水量(0.1mm)", "ID20" , "最大1時間降水量(0.1mm)", "ID21",                          "最大10分間降水量(0.1mm)", "ID22", "降雪の深さ日合計(cm)", "ID23",  "日最深積雪(cm)","ID24",                          "天気概況符号1", "ID25", "天気概況符号2", "ID26", "大気現象コード1", "大気現象コード1",                          "大気現象コード2", "大気現象コード3", "大気現象コード4", "大気現象コード5",                          "降水強風時間", "ID27"]

        self.names = ["KanID","Kname","KanID_1","YYYY","MM","DD", "avrLhpa", "avrLhpaRMK", "avrShpa",                       "avrShpaRMK", "minShpa", "minShpaRMK", "avrKion", "avrKionRMK", "maxKion", "maxKionRMK",                       "minKion", "minKionRMK", "avrStem", "avrStemRMK", "avrRhum", "avrRhumRMK", "minRhum",                       "minRhumRMK", "avrSped", "avrSpedRMK", "maxSped", "maxSpedRMK", "maxMuki", "maxMukiRMK",                       "maxSSpd", "maxSSpdRMK", "maxSMuk", "maxSMukRMK", "avrClod", "avrClodRMK", "daylght",                       "daylghtRMK", "sunlght", "sunlghtRMK", "amtEva", "amtEvaRMK", "dayPrec", "dayPrecRMK",                       "maxHPrc", "maxHPrcRMK", "maxMPrc", "maxMPrcRMK", "talSnow", "talSnowRMK", "daySnow",                       "daySnowRMK", "tenki1", "tenki1RMK", "tenki2", "tenki2RMK", "apCode1", "apCode2", "apCode3",                       "apCode4", "apCode5", "strgTim", "strgTimRMK"]
                      
        self.items_jp = ["現地気圧(hPa)","海面気圧(hPa)",                          "気温(degC)","蒸気圧(hPa)",                          "相対湿度(0-1)","風向(0-360)","風速(m/s)",                          "雲量(0-1)","現在天気","露天温度(degC)",                          "日照時間(時間)","全天日射量(W/m2)",                          "降水量(mm/h)","風速u(m/s)","風速v(m/s)"]

        self.items = ["lhpa",                       "shpa","kion","stem","rhum",                       "muki","sped","clod","tnki",                       "humd","lght","slht","kous","u","v"]
        ### the values of rmk to be set as NaN (RMK=0, 1, 2)
        self.rmk_nan01 = ["0", "1"]  ### sghtとslhtの夜間はRMK=2なので，RMK=2を欠損値としない
        self.rmk_nan = ["0", "1", "2"]  ### clodとtnkiは3時間間隔で，観測なしのRMK=2を欠損値とする必要がある
        # self.__df, self.__df_org, self.__df_interp, self.__df_interp_1H = self.__create_df()
        ### __create_df()でDataFrameを作る
        self.__df_org, self.__df = self.__create_df()

    ### propertyの名称をcreate_dfでの名称から変更している．通常使うself.__df_interp_1Hをself.dfと簡単に呼べる様にするため
    @property
    def df_org(self):
        '''欠損値未処理のDataFrameにアクセスする'''
        return self.__df_org

    @property
    def df(self):
        '''欠損値処理したDataFrameにアクセスする'''
        return self.__df


    def to_csv(self, df, fo_path='./df.csv'):
        '''DataFrame dfをCSV出力するmethod
           引数 df: DataFrame（必須）, fo_path=出力先ファイルのpath'''
        df.to_csv(fo_path, encoding='utf-8', )  ### CSVで出力する．デフォルトではWindows版ではShiftJISとなるため，UTF-8を明示する．
        cmd = 'nkf -w -Lu --overwrite ' + fo_path  ### 改行コードをLinuxタイプのLFに変更しておく（Linuxとの互換性のため）
        subprocess.call(cmd)

    def read_csv(self, fi_path):
        '''メソッドto_csvで出力したcsvファイルを読み込みDataFrameを返す
           引数 fi_path=CSV fileのpath  戻り値 DataFrame
        '''
        try:
            return pd.read_csv(fi_path, index_col=0, parse_dates=True)  ### 出力したCSVをDataFrameとして読み込む
        except:
            print('Error in reading csv of ', fi_path)

    '''以下は隠避されたmethod．意味が分からなくても使うには困らない'''

    def __unit_conversion(self, df):
        '''DataFrameを受け取り，カラムの単位を変換する．風速ベクトルを定義する．'''
        df['avrLhpa']=df['avrLhpa']/1.0e1 # [0.1hPa] -> [hPa]
        df['avrShpa']=df['avrShpa']/1.0e1 # [0.1hPa] -> [hPa]
        df['minShpa']=df['minShpa']/1.0e1 # [0.1hPa] -> [hPa]
        df['avrKion']=df['avrKion']/1.0e1 # [0.1degC] -> [degC]
        df['maxKion']=df['maxKion']/1.0e1 # [0.1degC] -> [degC]
        df['minKion']=df['minKion']/1.0e1 # [0.1degC] -> [degC]
        df['avrStem']=df['avrStem']/1.0e1 # [0.1hPa] -> [hPa]
        df['avrRhum']=df['avrRhum']/1.0e2 # [%] -> [0-1]
        df['avrSped']=df['avrSped']/1.0e1 # [0.1m/s] -> [m/s]
        df['maxSped']=df['maxSped']/1.0e1 # [0.1m/s] -> [m/s]
        df['maxMuki']=-90.0 - df['maxMuki'] * 22.5 # [0-16] -> [deg]  0=NA, 1=NNE, .., 8=S, ..., 16=N
        df['maxMuki']=df['maxMuki'] % 360.0 # 0-360
        df['maxSSpd']=df['maxSSpd']/1.0e1 # [0.1m/s] -> [m/s]
        df['maxSMuk']=-90.0 - df['maxSMuk'] * 22.5 # [0-16] -> [deg]  0=NA, 1=NNE, .., 8=S, ..., 16=N
        df['maxSMuk']=df['maxSMuk'] % 360.0 # 0-360
        df['avrClod']=df['avrClod']/1.0e1 # [0-10] -> [0-1]
        df['daylght']=df['daylght']/1.0e1 # 0.1h -> h
        ### 全天日射量日別値の単位について：1961-1980は1cal/cm2，1981以降は0.1MJ/m2
        ### 左辺は df.loc[,] が必要
        ### df['1981':]['sunlght']=df['1981':]['sunlght']*1.0e5/3.6e3/24.0 ### [0.1MJ/m2/day] -> [J/m2/s] = [W/m2]
        ### df[:'1980']['sunlght']=df[:'1980']['sunlght']*4.2*1.0e4/3.6e3/24.0 ### [1calcm2/day] -> [J/m2/s] = [W/m2]
        df.loc['1981':, 'sunlght']=df['1981':]['sunlght']*1.0e5/3.6e3/24.0 ### [0.1MJ/m2/day] -> [J/m2/s] = [W/m2]
        df.loc[:'1980', 'sunlght']=df[:'1980']['sunlght']*4.2*1.0e4/3.6e3/24.0 ### [1calcm2/day] -> [J/m2/s] = [W/m2]
        df['amtEva']=df['amtEva']/1.0e1 # 0.1mm -> 1 mm
        df['dayPrec']=df['dayPrec']/1.0e1 # 0.1mm -> 1mm
        df['maxHPrc']=df['maxHPrc']/1.0e1 # 0.1mm -> 1mm
        df['maxMPrc']=df['maxMPrc']/1.0e1 # 0.1mm -> 1mm
        df['talSnow']=df['talSnow'] # cm
        df['daySnow']=df['daySnow'] # cm           
        ### wind vector (u,v)
        rad = df["maxMuki"].values * 2 * np.pi / 360.0
        (umax, vmax) = df["maxSped"].values * (np.cos(rad), np.sin(rad))
        df["umax"] = umax
        df["vmax"] = vmax
        (u, v) = df["avrSped"].values * (np.cos(rad), np.sin(rad))
        df["u"] = u
        df["v"] = v

        return df
    
    def __create_df(self):
        start = self.datetime_ini
        end   = self.datetime_end
        ### Ys, Yeの妥当性と読込みcsvファイルの存在チェック
        if start >= end:
            print("ERROR: start >= end is incorrect.")
            sys.exit()
        Ys, Ye = int(start.strftime("%Y")), int(end.strftime("%Y"))
        fdir = self.dir + self.stn + "/"  # data dir
        print("Data directory path = ", fdir)
        fstart = glob.glob(fdir + self.stn + str(Ys) + ".csv")
        if len(fstart) != 1:
            print(fstart)
            print('ERROR: fstart file does not exist or has more than one file.')
            sys.exit()
        fend = glob.glob(fdir + self.stn + str(Ye) + ".csv")
        if len(fend) != 1:
            print('fend= ', fend)
            print('ERROR: fend file does not exist or has more than one file.')
            sys.exit()

        tsa_org = []  ### RMKの欠損値を考慮しない，オリジナルと同一
        fyears = list(range(Ys, Ye+1)) # from Ys to Ye

        for year in fyears:
            file = fdir + self.stn + str(year) + ".csv"
            print("Reading csv file of ", file)
            tsa_org.append(pd.read_csv(file, header = None, names = self.names, parse_dates=[[3,4,5]]))
            
        def create_df(tsa):
            '''Create df from tsa'''
            df = pd.concat(tsa)
            #df.index = [x + y * Hour() for x,y in zip(df['YYYY_MM_DD'],df['HH'])]
            df.index = df['YYYY_MM_DD']
            df.drop("YYYY_MM_DD", axis=1, inplace=True)
            #df.drop("HH", axis=1, inplace=True)
            df=df[start:end]
            return df
        df_org = create_df(tsa_org)  ### 欠損値を無視した，元データと同じDataFrame

        df_org = self.__unit_conversion(df_org)
        
        ### 欠損値を考慮したDataFrame
        df = df_org.copy()  ### df = df_org はcopyではない！
        rmk_cols = [col for col in df.columns if 'RMK' in col]  ### RMKカラムのリストを作成
        missing_rmk = [0, 1]
        df = super().set_missing_values(df, rmk_cols, missing_rmk)

        return df_org, df


class Data1Ds:
    '''Class for 1-D scalar data
       Use subclass Data1D for constructing instance for scalar or vector
    '''
    def __init__(self, df=None, col_1 = None, xrange: tuple = (0, -1)):
        '''df: pandas DataFrame, col_1: selected column of df and its value is v1, 
           xrange: apply x range of df index or full range of index (0, -1)'''
        if xrange == (0, -1):  ### default x full range
            self.df = df[df.index[0]:df.index[-1]]
        else:  ### x range set via argument
            self.df = df[xrange[0]:xrange[1]]
        self.xrange = (self.df.index[0], self.df.index[-1])
        (self.xmin, self.xmax) = self.xrange
        if type(self.df.index) == pd.DatetimeIndex:
            self.x = self.df.index.to_pydatetime()  ### pandas datetimeindex => datetime.datetime
        else:
            self.x = self.df.index
        self.v1 = self.df[col_1].values
        self.v1max = max(self.v1)
        self.v1min = min(self.v1)
        self.v1range = (self.v1min, self.v1max)
        self.vrange = self.v1range  ### to set y-range automatically by default

class Data1D(Data1Ds):
    '''Organize 1-D scalar or vector data.  
       初期化メソッドの引数にcol_2が存在しない場合はスカラー，存在する場合はベクトルと自動判定
    '''
    def __init__(self, df=None, col_1 = None, col_2 = None, xrange: tuple = (0, -1)):
        ''' USAGE: scalar = Data1D(df, 'kion'), vector = Data1D(df, 'u', 'v')'''
        super().__init__(df, col_1, xrange)
        if col_2:
            self.v2 = self.df[col_2].values
            self.v2max = max(self.v2)
            self.v2min = min(self.v2)
            self.v2range = (self.v2min, self.v2max)
            self.v = np.sqrt(self.v1**2 + self.v2**2)  ### v: magnitude of vector
            vmax = max(self.v)
            self.vrange = (-vmax, vmax)  ### useful for scaling vertical axis of vector



class Data1D_PlotConfig:
    def __init__(self, fig_size: tuple=(10,2), title_size: int=14, label_size: int=12,                  plot_color = 'b', xlabel = None, ylabel = None, v_color = 'k', vlabel = None,                  vlabel_loc = 'lower right', xlim: tuple = None, ylim: tuple = None,                  x_major_locator = None, y_major_locator = None,                  x_minor_locator = None, y_minor_locator = None,                  grid = False, format_xdata = None, format_ydata = None):
        self.fig_size = fig_size
        self.title_size = title_size
        self.label_size = label_size
        self.plot_color = plot_color
        self.xlabel = xlabel
        self.ylabel = ylabel
        self.v_color = v_color  ### color for fill_between of magnitude v
        self.vlabel = vlabel
        self.vlabel_loc = vlabel_loc
        self.xlim = xlim
        self.ylim = ylim
        self.x_major_locator = x_major_locator
        self.y_major_locator = y_major_locator
        self.x_minor_locator = x_minor_locator
        self.y_minor_locator = y_minor_locator
        self.grid = grid
        self.format_xdata = format_xdata
        self.format_ydata = format_ydata



class Plot1D:
    def __init__(self, plot_config, data):
        self.cfg = plot_config
        self.data = data
        self.figure = plt.figure(figsize=self.cfg.fig_size)

    def get_axes(self):
        return self.figure.add_subplot(1,1,1)
        
    def update_axes(self, axes):
        ### axes.set_ylim(self.data.v1range[0], self.data.v1range[1])
        ### axes.set_xlim(parse("2014-01-15"), parse("2014-01-16"))
        if self.cfg.xlim:
            axes.set_xlim(self.cfg.xlim)
        else:
            axes.set_xlim(self.data.x[0], self.data.x[-1])  ### default: full range
        if self.cfg.ylim:
            axes.set_ylim(self.cfg.ylim)
        else:
            axes.set_ylim(self.data.vrange[0], self.data.vrange[1])  ### default
        axes.grid(self.cfg.grid)
        if self.cfg.xlabel:
            axes.set_xlabel(self.cfg.xlabel, fontsize = self.cfg.label_size)
        if self.cfg.ylabel:
            axes.set_ylabel(self.cfg.ylabel, fontsize = self.cfg.label_size)
        if self.cfg.format_xdata:
            axes.format_xdata = self.cfg.format_xdata  ### DateFormatter('%Y-%m-%d')
        if self.cfg.format_ydata:
            axes.format_ydata = self.cfg.format_ydata
        if self.cfg.x_major_locator:
            axes.xaxis.set_major_locator(self.cfg.x_major_locator)
        if self.cfg.y_major_locator:
            axes.yaxis.set_major_locator(self.cfg.y_major_locator)
        if self.cfg.x_minor_locator:
            axes.xaxis.set_minor_locator(self.cfg.x_minor_locator)  ### days
        if self.cfg.y_minor_locator:
            axes.yaxis.set_minor_locator(self.cfg.y_minor_locator)
        #fig.autofmt_xdate()
        return axes

    def make_plot(self, axes):
        return axes.plot(self.data.x, self.data.v1, color=self.cfg.plot_color)

    def make_quiver(self, axes):
        ### Plot vectors and unit vector
        #print(type(self.data.x[0]))
        if isinstance(self.data.x[0], datetime.datetime):  ### check whether dtype of x is datetime.datetime.
            x = date2num(self.data.x)
        else:
            x = self.data.x
        self.q = axes.quiver(x, 0, self.data.v1, self.data.v2,                              color=self.cfg.plot_color, units='y', scale_units='y', scale=1, headlength=1,                              headaxislength=1, width=0.1, alpha=0.5)
        return self.q

    def make_quiverkey(self, axes):
        return axes.quiverkey(self.q, 0.2, 0.1, 5, '5 m/s', labelpos='W')

    def make_fill_between(self, axes):
        fill = axes.fill_between(date2num(self.data.x), self.data.v, 0, color= self.cfg.v_color, alpha=0.1)
        ### Fake box to insert a legend
        p = axes.add_patch(plt.Rectangle((1,1), 1, 1, fc=self.cfg.v_color, alpha=0.1))
        leg = axes.legend([p], [self.cfg.vlabel], loc=self.cfg.vlabel_loc)
        leg._drawFrame=False

    def save_plot(self, filename, **kwargs):
        axes = self.update_axes(self.get_axes())
        plot = self.make_plot(axes)
        self.figure.savefig(filename, **kwargs)

    def save_vector_plot(self, filename, magnitude=None, **kwargs):
        axes = self.update_axes(self.get_axes())
        quiver = self.make_quiver(axes)
        quiverkey = self.make_quiverkey(axes)
        if magnitude:
            fill_between = self.make_fill_between(axes)
        self.figure.savefig(filename, **kwargs)
