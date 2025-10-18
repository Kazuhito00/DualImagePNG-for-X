> [!NOTE]
> このリポジトリはGemini CLIを用いて作成された試験的なリポジトリです

# DualImagePNG-for-X
X（旧Twitter）で白背景と黒背景で異なる表示のトリック画像を作るスクリプト ※ダークモード不可
<img width="320" height="240" alt="image" src="https://github.com/user-attachments/assets/25c0d54f-930c-4c77-9543-0968725fe298" /><img width="320" height="240" alt="image" src="https://github.com/user-attachments/assets/cecc7fed-e70d-4751-ae9b-5ad194e3fd24" /><br>
<img width="320" height="240" alt="image" src="https://github.com/user-attachments/assets/a58320c2-284b-414b-a858-ce7e13d89e3a" /><img width="320" height="240" alt="image" src="https://github.com/user-attachments/assets/3cae418f-6ebb-4dd6-b856-c47d1336b448" />

## How it works
このスクリプトは、2枚の入力画像（白背景用と黒背景用）をもとに、PNGのトリック画像を生成します。
Webブラウザなどがこの画像を表示するとき、以下の式に基づいて最終的な表示色を計算します。

`表示色 = ピクセルの色 × 透明度 + 背景色 × (1 - 透明度)`

このスクリプトは、この計算式を逆算することで、トリック画像を作成します。

1.  **白背景のとき** (`背景色=白`):
    `白背景用の入力画像 = ピクセルの色 × 透明度 + 白 × (1 - 透明度)`
2.  **黒背景のとき** (`背景色=黒`):
    `黒背景用の入力画像 = ピクセルの色 × 透明度 + 黒 × (1 - 透明度)`

この2つの連立方程式を解くことで、2枚の入力画像から、「ピクセルの色」と「透明度」の組み合わせを算出します。

## Install

1.  リポジトリをクローンします:
    ```bash
    git clone https://github.com/Kazuhito00/DualImagePNG-for-X
    cd DualImagePNG-for-X
    ```

2.  依存関係をインストールします(NumPy, Pillow):
    ```bash
    pip install -r requirements.txt
    ```

### Usage
以下のコマンド形式でスクリプトを実行します。

```bash
python main.py -w <白背景用画像> -b <黒背景用画像> -o <出力ファイル名.png> [オプション]
```

-   `-w`, `--white`: 白背景のときに表示したい画像のパス
-   `-b`, `--black`: 黒背景のときに表示したい画像のパス
-   `-o`, `--out`: 出力するPNG画像のパス
-   `-ig`, `--input-grayscale`: (オプション) 入力画像をグレースケールとして処理 ※出力もグレースケール
-   `-q`, `--quantize`: (オプション) ファイルサイズを削減するために256色に減色

---

### Examples

#### カラー画像の生成

```bash
python main.py -w=assets/01.jpg -b=assets/02.jpg -o=assets/output_color.png
```

#### グレースケール画像の生成

```bash
python main.py -w=assets/01.jpg -b=assets/02.jpg -ig -o=assets/output_grayscale.png
```
# Note
サンプル画像は[ぱくたそ](https://www.pakutaso.com/)様の以下画像を使用しています。
* [まったく盛り上がらない無反応パーティーをご覧ください](https://www.pakutaso.com/20240233033post-50462.html)
* [急な展開で思わず反応してしまう男女](https://www.pakutaso.com/20240245033post-50463.html)

# Author
高橋かずひと(https://twitter.com/KzhtTkhs)

## License

[Apache License 2.0](LICENSE)
