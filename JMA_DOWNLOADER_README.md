# 気象庁データダウンローダー (JMA Weather Data Downloader)

気象庁の「過去の気象データ検索」サービス（etrn）から時別値（hourly data）を自動ダウンロードするツールです。

## 概要

このツールは、気象庁の公開データを自動的にダウンロードし、CSV形式で保存します。
- **データソース**: 気象庁 過去の気象データ検索 (etrn)
- **データ形式**: 時別値（1時間ごとの観測データ）
- **出力形式**: CSV (UTF-8 with BOM)

## 特徴

- 主要観測地点のプリセット（東京、横浜、千葉、大阪、名古屋、福岡、札幌）
- カスタム観測地点の指定が可能
- 複数年のデータを一括ダウンロード
- 自動リトライ機能（ネットワークエラー時）
- サーバー負荷軽減のための待機時間設定

## インストール

```bash
# 必要なパッケージのインストール
pip install -r requirements_jma_downloader.txt
```

## 使用方法

### 基本的な使い方

```bash
# 東京の2023年データをダウンロード
python jma_weather_downloader.py --year 2023 --station tokyo

# 大阪の2020-2023年のデータをダウンロード
python jma_weather_downloader.py --year 2020 2021 2022 2023 --station osaka
```

### カスタム観測地点の指定

都道府県番号（prec_no）と観測地点番号（block_no）を指定することで、プリセット以外の観測地点のデータも取得できます。

```bash
# カスタム観測地点の例
python jma_weather_downloader.py --year 2023 --prec_no 44 --block_no 47662 --name 東京
```

### オプション

- `--year`: ダウンロード対象の年（複数指定可能）
- `--station`: プリセット観測地点名
- `--prec_no`: 都道府県番号（カスタム地点）
- `--block_no`: 観測地点番号（カスタム地点）
- `--name`: 観測地点名（カスタム地点）
- `--output`: 出力ディレクトリ（デフォルト: jma_data）
- `--delay`: リクエスト間の待機時間（秒、デフォルト: 1.0）
- `--gwo-format`: GWO形式（33列、雲量補間あり）で保存
- `--stations-config`: `stations.yaml` の代わりに使用するカタログファイル
- `--list-stations`: 利用可能な観測地点を一覧表示

## 観測地点カタログ

`stations.yaml` には GWO/AMD で取り扱う 150 以上の観測地点が記載されており、`prec_no` / `block_no`、座標、`gwo_stn.csv` と `smaster.index` から抽出した特記事項（年月範囲付き）が含まれます。

- 一覧表示: `python jma_weather_downloader.py --list-stations`
- 別の YAML を使用: `python jma_weather_downloader.py --stations-config custom.yaml ...`
- カタログ再生成: `python scripts/build_station_catalog.py`

ダウンロード時には対象年と重なる特記事項が `[info] Special remarks ...` として表示され、観測所の移転や装置変更を確認できます。

## 観測地点コードの調べ方

気象庁の「過去の気象データ検索」サイトで、以下の手順で確認できます：
1. https://www.data.jma.go.jp/stats/etrn/index.php にアクセス
2. 希望する都道府県と観測地点を選択
3. URLパラメータの `prec_no` と `block_no` を確認

## 取得データの項目

時別値データには以下の項目が含まれます（観測地点により異なる場合があります）：
- 気圧（現地・海面）
- 降水量
- 気温
- 露点温度
- 蒸気圧
- 湿度
- 風向・風速
- 日照時間
- 全天日射量
- 雪（降雪・積雪）
- 天気
- 雲量
- 視程

## 注意事項

### ダウンロード時間

1年分のデータ取得には、約6-10分程度かかります（365日 × 待機時間1秒/日）。
- `--delay` オプションで待機時間を調整可能ですが、気象庁サーバーへの負荷を考慮し、最低0.5秒以上を推奨します。

### データ形式について

- 欠測値は「--」または空欄で表示されます
- 気象庁互換形式については、[値欄の情報](https://www.data.jma.go.jp/obd/stats/data/mdrr/man/remark.html)を参照してください

### 利用規約

気象庁のデータ利用規約に従ってご利用ください。
- [気象庁ウェブサイトの利用規約](https://www.jma.go.jp/jma/kishou/info/coment.html)

## トラブルシューティング

### エラー: "No table found"

観測地点または期間が存在しない可能性があります。観測開始時期を確認してください。

### エラー: "Request failed"

ネットワークエラーの可能性があります。自動リトライを実行しますが、継続する場合は時間を置いてから再実行してください。

## テスト

簡易テストスクリプトが含まれています：

```bash
# 2023年1月1日の東京のデータを取得（テスト用）
python test_jma_downloader.py
```

## ライセンス

このツールはMITライセンスの下で公開されています。
データの著作権は気象庁に帰属します。

## 参考資料

- [気象庁 過去の気象データ検索](https://www.data.jma.go.jp/stats/etrn/index.php)
- [気象庁 値欄の情報](https://www.data.jma.go.jp/obd/stats/data/mdrr/man/remark.html)
- [GWO-AMD プロジェクト](https://github.com/jsasaki-utokyo/GWO-AMD)
