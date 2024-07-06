# GWO-AMD
[GWO](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/) and [AMD](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/) GWO-AMD is a Japan Meteorological Agency's meteorological dataset handling tool.
Explanation is given in Japanese as this dataset is provided in Japanese only.

## 気象庁互換形式
- 2022年のデータもウェザートーイWEBのサポートで配布されていますが，気象庁互換形式です．値欄に数値以外の記号が含まれており，要注意です．
- [**値欄の情報**](https://www.data.jma.go.jp/obd/stats/data/mdrr/man/remark.html)

## 気象データベース地上観測（GWO）とアメダス（AMD）の準備
- 気象データベース地上観測（GWO）およびアメダス（AMD）から**SQLViewer7.exe**で切り出した，全地点全期間（ただし，1990年以前と1991年以降の2つのファイルに分割）のCSVファイルを読み込み，観測点別年別のCSVファイルとして切り出す，**Jupyter Notebook**を用意しました．
- 切り出したCSVの単位は元のデータベースの単位です．[**気象庁互換**](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top2_11.html)はわかりやすいですが，2022年度以降に採用することとします．すなわち，地点別年別のCSVファイルの形式は2021年以前と2022年以降で異なっており，これらを読み込むコードで対応する方針とします．これは過去の蓄積を最大限生かすためです．この読み込むコードはmod_class_met.pyです．
- [**気象庁互換**](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top2_11.html)は最新の気象庁WEBで公開されており，換算不要のわかりやすい単位です．
- GWOには対応していますが，他は未完成です．
- これは商用データベースで，既に販売は終了していますが，購入者は[ウェザートーイWEB](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/)でサポート情報を入手できます．詳細は[こちら](https://estuarine.jp/2016/05/gwo/)を参照ください．
- データの詳細は[GWO](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top5_1.htm)および[AMD](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top2_1.htm)を参照ください．

## データベースの詳細情報

### [GWO](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top5_1.htm)
#### [日別データベース](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/gwodb.htm#2_1)

- 全天日射量の単位に付いての注意

```
1961年～1980年  1 cal/c㎡
1981年～2009年  0.1MJ/㎡
2010年以降は    0.01MJ/㎡
```
- 最低海面気圧の注意
```
1961年～2002年では、10000以上は、10000引かれています
（オンラインデータの2003年～2005年も10000以上は、10000引かれています）
```

#### [時別データベース](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/gwodb.htm#2_2)
```
◇１９６１年～１９９０年　３時間置きです
(※1)ただしこの期間の日照時間、全天日射量、降水量のデータはありません。
◇１９９１年～２０ｎｎ年　１時間置きです
◇雲量／現在天気は、3時～21時で3時間置きです
```

### [AMD](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top2_1.htm)

準備中

## 使い方
- **GWO_multiple_stns_to_stn.ipynb**で，SqlView7.exeで切り出した全観測点全期間のCSVファイルを読み込み，観測点別のCSVファイルとして，指定されたディレクトリに出力する．
- **GWO_div_year.ipynb**で，観測点別ディレクトリに年別CSVファイルとして出力する．
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

