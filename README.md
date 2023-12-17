# GWO-AMD
[GWO](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/) and [AMD](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/) GWO-AMD is a Japan Meteorological Agency's meteorological dataset handling tool.
Explanation is given in Japanese as this dataset is provided in Japanese only.

## 気象データベース地上観測（GWO）とアメダス（AMD）の準備
- 気象データベース地上観測（GWO）およびアメダス（AMD）から**SQLViewer7.exe**で切り出した，全地点全期間（ただし，1990年以前と1991年以降の2つのファイルに分割）のCSVファイルを読み込み，観測点別年別のCSVファイルとして切り出す，**Jupyter Notebook**を用意しました．
- Linuxを前提としていますが，pathを修正すればWindowsでも動くはずです．
- GWOには対応していますが，他は未完成です．
- これは商用データベースで，既に販売は終了していますが，購入者は[ウェザートーイWEB](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/)でサポート情報を入手できます．詳細は[こちら](https://estuarine.jp/2016/05/gwo/)を参照ください．
- データの詳細は[GWO](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top5_1.htm)および[AMD](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top2_1.htm)を参照ください．

## 使い方
- **GWO_div_year.ipynb**で，各観測点における全期間のCSVファイル（ファイル名の例：Tokyo1991-2021.csv）を出力します．
- 次に，**GWO_multiple_stns_to_stn.ipynb**で，これらのCSVファイルをすべて読み込み，各観測点における各年のCSVファイルとして出力します．
- 詳細はそれぞれのJupyter Notebookを参照ください．

## 注意
- **2019/01/11:** 千葉の2010年，2011年の時別値CSVデータファイルに欠損行があったので，欠損行をチェックするclass Met_GWO_check(Met_GWO)を**mod_class_met.py**に追加した．
- 詳細は../GWO/Hourly/Chiba/readme.txt を参照（GitHubには無し）
- Since there were missing rows in the time series CSV data files for Chiba in 2010 and 2011, a class of Met_GWO_check (Met_GWO) is added in **mod_class_met.py** to check such missing rows.

## Plotツール
- 簡単なプロットツール **run_hourly_met.ipynb** を用意しました．**mod_class_met.py**を読み込みます．
- A simple GWO hourly meteorological data plotting and processing tool of **run_hourly_met.ipynb** is prepared, which imports **mod_class_met.py**.
- Hourly data directory path should be given:
```bash
dirpath = "/mnt/d/dat/met/JMA_DataBase/GWO/Hourly/"
```

