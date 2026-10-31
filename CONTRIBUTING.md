# 🤝 植物診断ラボへの開発参加ガイド

植物診断ラボ（Tomato Diagnosis Lab）への関心をありがとうございます。

本プロジェクトは、トマトの生育状態をAIで診断するオープンソースのWebアプリケーションです。

誰でもプログラムを改良し、新しい機能や改善案を提案できます。

## 1. 開発に参加できること

以下のような改善を歓迎しています。

- AIモデルの精度向上や新しいモデルの導入
- 対応する植物や診断項目の追加
- 診断結果や栽培アドバイスの改善
- 画面デザインや操作性の向上
- 栽培記録やデータ分析機能の追加
- バグ修正、処理速度の改善
- ドキュメントやテストの追加

これらに限らず、自由なアイデアによる改善を歓迎します。

## 2. 開発への参加方法

### ① リポジトリをForkする

GitHubで本プロジェクトを開き、右上の「Fork」をクリックして、自分のアカウントにコピーしてください。

https://github.com/yuika200-cmyk/tomato-diagnosis-lab

### ② 自分の環境でプログラムを編集する

Python 3.11を推奨しています。

```bash
git clone https://github.com/YOUR_USERNAME/tomato-diagnosis-lab.git
cd tomato-diagnosis-lab
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

`YOUR_USERNAME` は自分のGitHubユーザー名に置き換えてください。

必要なAIモデルやライブラリについては、README.mdを確認してください。

### ③ 新しいブランチを作る

変更内容が分かる名前のブランチを作ってください。

```bash
git checkout -b feature/improve-diagnosis
```

### ④ プログラムを改良する

自由に変更を加えてください。変更後は、アプリが正常に動作することを確認してください。

AIの診断結果や収穫予測に関する変更では、可能な範囲で検証方法や結果も記録してください。

### ⑤ 変更をGitHubに送信する

```bash
git add .
git commit -m "Improve diagnosis features"
git push origin feature/improve-diagnosis
```

※ `git add .` を実行する前に、秘密情報や個人情報が含まれていないか確認してください。

### ⑥ Pull Requestを作成する

GitHubでPull Requestを作成し、元のリポジトリに改善を提案してください。

Pull Requestには、次の内容を記載してください。

- 何を改善したか

