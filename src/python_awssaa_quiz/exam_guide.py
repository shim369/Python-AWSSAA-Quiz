"""SAA-C03 試験ガイドのタスクステートメント(出題範囲の細目)。

出典: AWS Certified Solutions Architect - Associate (SAA-C03) 試験ガイド
https://docs.aws.amazon.com/aws-certification/latest/solutions-architect-associate-03/solutions-architect-associate-03.html
focus は試験ガイドの「Knowledge of / Skills in」から、出題されやすい観点を抜き出して要約したもの。
試験ガイドが改訂されたら、ここを合わせて直す。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

GUIDE_URL = (
    "https://docs.aws.amazon.com/aws-certification/latest/"
    "solutions-architect-associate-03/solutions-architect-associate-03.html"
)


class Domain(StrEnum):
    """SAA-C03 の出題分野(ドメイン)。"""

    SECURE = "secure"
    RESILIENT = "resilient"
    PERFORMANT = "performant"
    COST = "cost"

    @property
    def label(self) -> str:
        return DOMAIN_LABELS[self]

    @property
    def weight(self) -> float:
        return DOMAIN_WEIGHTS[self]


DOMAIN_LABELS = {
    Domain.SECURE: "セキュアなアーキテクチャの設計",
    Domain.RESILIENT: "弾力性に優れたアーキテクチャの設計",
    Domain.PERFORMANT: "高性能なアーキテクチャの設計",
    Domain.COST: "コストを最適化したアーキテクチャの設計",
}

# 試験ガイドに書かれている出題比率
DOMAIN_WEIGHTS = {
    Domain.SECURE: 0.30,
    Domain.RESILIENT: 0.26,
    Domain.PERFORMANT: 0.24,
    Domain.COST: 0.20,
}


@dataclass(frozen=True)
class Task:
    id: str  # "1.1"
    domain: Domain
    title: str
    focus: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"{self.id} {self.title}"


TASKS: dict[str, Task] = {
    t.id: t
    for t in (
        Task("1.1", Domain.SECURE, "AWSリソースへのセキュアなアクセスの設計", (
            "複数アカウントのアクセス管理(Organizations、SCP、Control Tower)",
            "IAMユーザー・グループ・ロール・ポリシー、最小権限、ルートユーザーのMFA",
            "STSとロールの切り替え、クロスアカウントアクセス",
            "IAM Identity Center、ディレクトリサービスとのフェデレーション",
            "リソースベースのポリシー、責任共有モデル",
        )),
        Task("1.2", Domain.SECURE, "セキュアなワークロードとアプリケーションの設計", (
            "セキュリティグループ・ネットワークACL・ルートテーブル・NATゲートウェイを使ったVPC設計",
            "パブリック/プライベートサブネットによるネットワーク分割、VPCエンドポイント",
            "認証情報の保護(Secrets Manager)、アプリのアクセス制御(Cognito)",
            "外部の脅威への対策(Shield、WAF、GuardDuty、Macie)",
            "AWSとの外部接続の保護(VPN、Direct Connect)",
        )),
        Task("1.3", Domain.SECURE, "適切なデータセキュリティ管理の決定", (
            "保存時の暗号化(KMS)と転送時の暗号化(ACMとTLS)",
            "暗号化キーのアクセスポリシー、キーのローテーションと証明書の更新",
            "バックアップとレプリケーション、データの保持・分類・ライフサイクル",
            "コンプライアンス要件に合わせた技術の選択",
        )),
        Task("2.1", Domain.RESILIENT, "スケーラブルで疎結合なアーキテクチャの設計", (
            "SQS・SNS・EventBridgeによる疎結合とイベント駆動アーキテクチャ",
            "API Gateway、Lambda・Fargateなどのサーバーレス",
            "ECS・EKSによるコンテナ化、Step Functionsによるワークフロー",
            "水平/垂直スケーリング、ALB、キャッシュ、CDN、リードレプリカ",
            "オブジェクト/ファイル/ブロックストレージの使い分け、目的別のマネージドサービス",
        )),
        Task("2.2", Domain.RESILIENT, "高可用性と耐障害性のあるアーキテクチャの設計", (
            "マルチAZ・マルチリージョン構成、Route 53によるフェイルオーバー",
            "DR戦略(バックアップと復元、パイロットライト、ウォームスタンバイ、アクティブ/アクティブ)とRPO/RTO",
            "単一障害点の排除、RDS Proxy、イミュータブルインフラ",
            "データの耐久性と可用性(バックアップ、レプリケーション)",
            "変更できないレガシーアプリの信頼性向上、サービスクォータとスロットリング",
        )),
        Task("3.1", Domain.PERFORMANT, "高性能でスケーラブルなストレージの決定", (
            "S3・EFS・EBS・FSxの性能特性と使い分け",
            "ハイブリッドストレージ(Storage Gateway)",
            "将来の増加に対応できるストレージ構成",
        )),
        Task("3.2", Domain.PERFORMANT, "高性能で伸縮性のあるコンピューティングの設計", (
            "EC2 Auto Scaling・AWS Auto Scalingとスケーリングの指標",
            "インスタンスタイプやLambdaのメモリ量の選択",
            "Batch、EMR、Fargate、ECS/EKSの使い分け",
            "キューによる疎結合で各コンポーネントを独立にスケールさせる",
        )),
        Task("3.3", Domain.PERFORMANT, "高性能なデータベースの決定", (
            "読み込み中心/書き込み中心のアクセスパターンに合わせた設計",
            "リードレプリカ、ElastiCache・DAXによるキャッシュ",
            "Aurora・DynamoDBなどデータベースの種類とエンジンの選択",
            "キャパシティ計画(キャパシティユニット、プロビジョンドIOPS)、接続とプロキシ",
        )),
        Task("3.4", Domain.PERFORMANT, "高性能でスケーラブルなネットワークの決定", (
            "CloudFrontとGlobal Acceleratorの使い分け",
            "サブネットの階層、ルーティング、IPアドレス設計",
            "ロードバランサーの選択(ALB/NLB/GWLB)",
            "VPN、Direct Connect、PrivateLinkなどの接続方法",
        )),
        Task("3.5", Domain.PERFORMANT, "高性能なデータの取り込みと変換の決定", (
            "Kinesisによるストリーミング、取り込みの頻度と規模",
            "Glueによる変換(CSVからParquetなど)、Athena・Lake Formationによるデータレイク",
            "DataSync・Storage Gatewayによるデータ転送",
            "EMRによるデータ処理、QuickSightによる可視化",
        )),
        Task("4.1", Domain.COST, "コストを最適化したストレージの設計", (
            "S3ストレージクラスとライフサイクルポリシー、コールド階層",
            "EBSのボリュームタイプ(SSD/HDD)、EFS・FSxの選択",
            "最も安いデータ転送・移行の方法(DataSync、Transfer Family、Snowファミリー)",
            "バックアップとアーカイブ、リクエスタ支払い",
        )),
        Task("4.2", Domain.COST, "コストを最適化したコンピューティングの設計", (
            "購入オプション(スポット、リザーブドインスタンス、Savings Plans)",
            "インスタンスファミリーとサイズの選択、休止(ハイバネーション)",
            "Lambda・Fargate・EC2のコスト比較",
            "本番/非本番で必要な可用性の違い、Outposts",
        )),
        Task("4.3", Domain.COST, "コストを最適化したデータベースの設計", (
            "DynamoDBとRDSの比較、サーバーレスのデータベース",
            "バックアップと保持期間(スナップショットの頻度)",
            "時系列・列指向などデータ形式に合ったデータベース",
            "異なるエンジンへの移行(DMS、SCT)",
        )),
        Task("4.4", Domain.COST, "コストを最適化したネットワークの設計", (
            "NATゲートウェイの構成(共有かAZごとか)、NATインスタンスとの比較",
            "Direct Connect・VPN・インターネットの選択と帯域",
            "データ転送料金を抑える経路(VPCエンドポイント、AZ間・リージョン間通信)",
            "Transit GatewayとVPCピアリング、CDNとエッジキャッシュ",
        )),
    )
}


def tasks_for(domain: Domain) -> list[Task]:
    return [t for t in TASKS.values() if t.domain is domain]
