弦グラフと木幅の理論と応用
Source: https://claude.ai/chat/0ed06c6d-1036-4f03-baf4-681db0d70983
Exported: 2026-09-18T11:15:30.544Z
User
弦グラフと木幅に関して解説した一次資料があれば教えてください．無向グラフにおける木幅の正確なな定義と弦グラフに対しては完全Elimination Orderが存在すること，さらに，弦グラフに対して最大独立集合をを求める効率的アルゴリズム，k彩色問題を解くアルゴリズムとその一次資料について教えてください．
Claude
1. 木幅（treewidth）の定義
一次資料は N. Robertson, P. D. Seymour, “Graph minors. II. Algorithmic aspects of tree-width,” Journal of Algorithms 7(3):309–322, 1986 (doi:10.1016/0196-6774(86)90023-4) です。この論文で tree-width が導入され、固定された平面グラフ H への縮約可能性判定の多項式時間アルゴリズム、および固定 w に対する tw ≤ w 判定の多項式アルゴリズムの（非構成的な）存在証明が与えられています。 irisaprinceton
定義（無向グラフ G = (V, E) に対して）：
組 (T, {X_t}_{t∈V(T)})（T は木、X_t ⊆ V は bag）が G の木分解であるとは、
⋃_{t∈V(T)} X_t = V
各辺 {u,v} ∈ E に対し、u, v ∈ X_t となる t ∈ V(T) が存在する
各 v ∈ V に対し、{t ∈ V(T) : v ∈ X_t} が T の連結部分木をなす（等価: t₂ が T 上で t₁–t₃ 路上にあれば X_{t₁} ∩ X_{t₃} ⊆ X_{t₂}）
この木分解の幅を max_t |X_t| − 1 と定め、木幅 tw(G) を G のすべての木分解の幅の最小値と定めます。−1 は木（tw = 1）を正規化するための補正です。
なお、同値な概念は独立に R. Halin, “S-functions for graphs,” Journal of Geometry 8(1–2):171–186, 1976 で与えられており、treewidth の文献では Halin の S-functions が先行研究として併記されます。 springer
弦グラフとの関係（重要）: tw(G) = min{ ω(H) − 1 : H は G の弦化（chordal completion, triangulation）} であり、弦グラフ G 自身については tw(G) = ω(G) − 1 が成り立ちます。つまり「木幅 ≤ k」は「max clique ≤ k+1 の弦グラフの部分グラフになる」＝「partial k-tree」と同値です。この同値性（k-tree との対応）の一次資料は S. Arnborg, D. G. Corneil, A. Proskurowski, “Complexity of finding embeddings in a k-tree,” SIAM J. Algebraic and Discrete Methods 8:277–284, 1987 で、同論文は k-tree への埋め込み（＝木幅計算）が NP 困難であることも示しています。固定 k での線形時間判定は H. L. Bodlaender, “A linear-time algorithm for finding tree-decompositions of small treewidth,” SIAM J. Comput. 25(6):1305–1317, 1996。 tsu

2. 弦グラフと完全消去順序（perfect elimination ordering, PEO）
定義: G が弦グラフ（chordal / triangulated / rigid circuit graph）とは、長さ 4 以上のすべての閉路が弦をもつこと。頂点 v が単体的 (simplicial) とは N(v) がクリークをなすこと。順序 v₁, …, v_n が PEO とは、各 i に対して v_i が G[{v_i, …, v_n}] で単体的であること。
一次資料：
G. A. Dirac, “On rigid circuit graphs,” Abh. Math. Sem. Univ. Hamburg 25:71–76, 1961. — 「任意の弦グラフは単体的頂点をもつ。完全グラフでなければ非隣接な単体的頂点が 2 個存在する」という基本補題。PEO の存在はここから帰納法で直ちに従います。Gavril らの初期論文でも Dirac 1961 が基礎文献として引かれています。 Wiley Online Library
D. R. Fulkerson, O. A. Gross, “Incidence matrices and interval graphs,” Pacific J. Math. 15(3):835–855, 1965. — 「G が弦グラフ ⟺ G が PEO をもつ」という特徴付け（いわゆる Fulkerson–Gross の定理）と、単体的頂点を繰り返し除去する O(n³) 認識アルゴリズム。
D. J. Rose, “Triangulated graphs and the elimination process,” J. Math. Anal. Appl. 32(3):597–609, 1970. — 消去過程（Gauss 消去の fill-in）と弦性の対応。疎行列分解の文脈との接続はここが原典です。
D. J. Rose, R. E. Tarjan, G. S. Lueker, “Algorithmic aspects of vertex elimination on graphs,” SIAM J. Comput. 5(2):266–283, 1976 (doi:10.1137/0205021)。STOC 1975 の予稿版あり。— LexBFS による O(n+m) 時間の PEO 生成と、その順序が PEO か否かの O(n+m) 検査。弦性認識の線形時間アルゴリズムの原典。 arxiv
R. E. Tarjan, M. Yannakakis, “Simple linear-time algorithms to test chordality of graphs, test acyclicity of hypergraphs, and selectively reduce acyclic hypergraphs,” SIAM J. Comput. 13(3):566–579, 1984 (doi:10.1137/0213035)。同誌 14(1):254–255 (1985) に Addendum があります。— MCS (maximum cardinality search)。LexBFS より実装が単純な線形時間 PEO 生成法で、clique tree の構成にもそのまま使えます。 arxiv
（構造的特徴付けとして、F. Gavril, “The intersection graphs of subtrees in trees are exactly the chordal graphs,” J. Combin. Theory Ser. B 16(1):47–56, 1974 も一次資料です。clique tree の存在＝木分解の存在という観点で、木幅との橋渡しになります。）

3. 最大独立集合・最小彩色の効率的アルゴリズム
両方とも同じ一次資料に収められています：
F. Gavril, “Algorithms for minimum coloring, maximum clique, minimum covering by cliques, and maximum independent set of a chordal graph,” SIAM J. Comput. 1(2):180–187, 1972 (doi:10.1137/0201013)
この論文は、弦グラフが与えられたとき、最小彩色・最小クリーク被覆・最大クリーク・最大独立集合を求める効率的アルゴリズムの構成法を示しています。 Semantic Scholar
最大独立集合（貪欲、PEO 順）
PEO を v₁, …, v_n とし、S := ∅、i を 1 から n へ走査。v_i が未削除なら S := S ∪ {v_i} とし、N[v_i] を削除する。
正当性: v_i は残存グラフで単体的なので N(v_i) はクリーク。任意の最大独立集合は N[v_i] から高々 1 頂点しか含まず、その頂点を v_i に置き換えても独立性は保たれる（exchange argument）。PEO 取得込みで O(n+m)。重み付き版も動的計画で線形時間に拡張できます。
最小彩色 / k-彩色
PEO の逆順 v_n, v_{n−1}, …, v₁ に対し、各頂点に「既に彩色済みの隣接頂点が使っていない最小番号の色」を割り当てる貪欲彩色。
正当性: v_i を彩色する時点で彩色済みの隣接頂点は残存グラフでの N(v_i) の一部であり、これはクリーク。よって使用色数は ω(G) を超えません。したがって
χ(G) = ω(G)（弦グラフは perfect）、かつ最適彩色が O(n+m) で得られる。
k-彩色問題の解法はこれで尽きます。ω(G) を計算し（PEO 上で max_i (1 + |{v_j ∈ N(v_i) : j > i}|)、これも線形時間）、k ≥ ω(G) なら上の貪欲彩色が k 彩色を与え、k < ω(G) なら不可能。弦グラフ上の k-彩色は線形時間で解けます（一般グラフでは k ≥ 3 で NP 完全）。
弦グラフが perfect であること（χ = ω が誘導部分グラフで遺伝）の一次資料は A. Hajnal, J. Surányi, “Über die Auflösung von Graphen in vollständige Teilgraphen,” Ann. Univ. Sci. Budapest, Sectio Math. 1:113–121, 1958 です。chordal graph 系の論文では標準的にこの文献が引かれます。 arxiv

4. 二次資料（体系的に読むなら）
M. C. Golumbic, Algorithmic Graph Theory and Perfect Graphs, Academic Press, 1980（第2版 Elsevier, 2004） — 第4章が弦グラフ。Dirac / Fulkerson–Gross / Gavril / RTL を統一的な記法で再構成しており、上記の定理群の証明を一冊で追えます。
J. R. S. Blair, B. Peyton, “An Introduction to Chordal Graphs and Clique Trees,” in Graph Theory and Sparse Matrix Computation, IMA Vol. Math. Appl. 56:1–27, Springer, 1993 — clique tree と PEO の関係を最も丁寧に解説した survey。木分解との対応を見るのに最適です。
H. L. Bodlaender, “A tourist guide through treewidth,” Acta Cybernetica 11:1–21, 1993、および “A partial k-arboretum of graphs with bounded treewidth,” Theoret. Comput. Sci. 209:1–45, 1998 — 木幅の同値定義（k-tree、bramble、searching number 等）の総覧。
R. Diestel, Graph Theory, 第12章（tree-decomposition の厳密な扱い）、Cygan et al., Parameterized Algorithms, Springer 2015, 第7章（木分解上の DP）。
min-max 定理としての P. D. Seymour, R. Thomas, “Graph searching and a min-max theorem for tree-width,” J. Combin. Theory Ser. B 58(1):22–33, 1993 — bramble/haven による木幅の下界証明に使えます。
並行プログラムの依存グラフに木幅の議論を持ち込む場合、実務上は「元のグラフを弦化 → clique tree 上で DP」という流れになるので、弦化最小化が NP 困難であること（M. Yannakakis, “Computing the minimum fill-in is NP-complete,” SIAM J. Alg. Disc. Meth. 2(1):77–79, 1981）も押さえておくとよいと思います。
User
コンパイラのSSAの議論の中で，特定の変数が生存する支配木の部分木で交差グラフを作ると弦グラフになり，弦グラフに対してk彩色問題が効率よく解けることでレジスタ割当に応用することを示した一次資料および解説があれば教えてください．一番最初にそのことを示したものがあれば教えてください．
Claude
結論を先に
「SSA 形式（strict SSA）の干渉グラフは弦グラフであり、したがって k 彩色＝レジスタ割当が多項式時間で解ける」という結果は、2005 年に 4 つのグループがほぼ同時・独立に発見しています。「最初に明示的に示した一次資料」としては、日付の上で
Sebastian Hack, “Interference Graphs of Programs in SSA-form,” Interner Bericht 2005-25 (ISSN 1432-7864), Universität Karlsruhe, June 2005.
https://compilers.cs.uni-saarland.de/papers/ifg_ssa.pdf
が弦性 (chordality) を定理として証明した最初の文献とみなされるのが通例です。同レポートでは Definition 7 で弦グラフを定義し、支配関係に関する補題（値 v が生存する全ラベルは定義点 D_v に支配される／2 つの値が同時生存なら D_v と D_w の間に支配関係がある）を積み上げて Theorem 1 (Chordality) を導いています。
同月の Philip Brisk, Foad Dabiri, Jamie Macbeth, Majid Sarrafzadeh, “Polynomial Time Graph Coloring Register Allocation,” 14th International Workshop on Logic and Synthesis (IWLS’05), June 2005 は、より弱い「SSA 干渉グラフは perfect である」を示したものです。Pereira–Palsberg 自身が「Brisk らが SSA 形式の strict program は perfect 干渉グラフをもつことを証明し、独立に Hack がより強い chordal であることを証明した」と整理しています。

ただし「本当の最初」は 1970 年代のグラフ理論
重要な注意があります。Bouchez–Darte–Rastello–Guillon は、この性質自体はグラフ理論と SSA を結びつければ新しい結果ではないと明言しています。彼らの説明では、Walter (1972)、Gavril (1974)、Buneman (1974) の定理（Golumbic の教科書 Theorem 4.8）により「あるグラフが弦グラフであることと、木の部分木族の交差グラフであることは同値」であり、ここで木＝支配木、部分木＝変数の生存範囲、極大クリーク＝プログラム点、と読み替えれば直ちに従う、とされています。彼ら自身も out-of-SSA 変換と coalescing の相互作用を調べる過程でこの性質を「再発見」したと書いています。
つまり、ご質問の「支配木の部分木の交差グラフ」という定式化そのものの一次資料は：
F. Gavril, “The intersection graphs of subtrees in trees are exactly the chordal graphs,” J. Combin. Theory Ser. B 16(1):47–56, 1974.
P. Buneman, “A characterisation of rigid circuit graphs,” Discrete Mathematics 9(3):205–212, 1974.
J. R. Walter, “Representations of rigid cycle graphs,” Ph.D. thesis, Wayne State University, 1972.
（k 彩色側は前回挙げた Gavril, SIAM J. Comput. 1(2):180–187, 1972）
コンパイラ側の前史としては K. Knobe, K. Zadeck, “Register Allocation Using Control Trees,” Tech. Report CS-92-13, Brown University, 1992 や、支配関係による干渉判定を使った Z. Budimlić et al., “Fast Copy Coalescing and Live Range Identification,” PLDI 2002, pp. 25–32 があり、必要な補題は事実上そこに現れています。

2005–2006 年の一次資料（4 グループ）
文献
時期
主張
Hack, Interference Graphs of Programs in SSA-form, TR 2005-25, Univ. Karlsruhe
2005-06
弦性を直接証明
Brisk, Dabiri, Macbeth, Sarrafzadeh, IWLS’05
2005-06
perfect 性を証明
Bouchez, Darte, Guillon, Rastello, Register Allocation and Spill Complexity under SSA, RR2005-33, LIP ENS-Lyon
2005-08
弦性＋spill 複雑性
Pereira, Palsberg, Register Allocation via Coloring of Chordal Graphs, APLAS 2005, LNCS 3780, pp. 315–329
2005-11
弦グラフ彩色に基づく実用アロケータ（Java 1.5 ライブラリで実測）
最も引用される「決定版」の一次資料は次の 2 本です：
S. Hack, D. Grund, G. Goos, “Register Allocation for Programs in SSA-Form,” CC 2006, LNCS 3923, pp. 247–262. — 干渉グラフが弦グラフであることから O(n²) の最適彩色が得られ、coloring / spilling / coalescing を完全に分離 (decouple) できることを示した論文。以降の SSA-based register allocation の枠組みはここが基準になっています。
S. Hack, G. Goos, “Optimal register allocation for SSA-form programs in polynomial time,” Information Processing Letters 98(4):150–155, 2006. — ご質問の趣旨に最も直接答える論文です。支配木の後行順 (post-order) 走査がそのまま完全消去順序 (PEO) を与えることを Theorem 15 として証明しており、弦グラフの PEO をコンパイラ側で明示的に構成しなくてよい（支配木が既にあるので追加コスト 0）という点が実装上の要点になります。
さらに体系的なものとして：
S. Hack, “Register Allocation for Programs in SSA Form,” Ph.D. thesis, Universität Karlsruhe, 2007. — 単著としては最も網羅的。
S. Hack, D. Grund, G. Goos, “Towards Register Allocation of SSA-form Programs,” Interner Bericht 2005-27, Univ. Karlsruhe, 2005 (DOI: 10.5445/IR/1000004125) — spilling / coloring / coalescing の 3 分割アーキテクチャの初出。

証明の骨子（Hack–Goos 版）
前提は strict SSA（start から任意の使用点に至る全パスが定義点を通る）であること。これが無いと成り立ちません。
各 SSA 変数 v には唯一の定義点 D_v がある。
補題: v が生存するラベル ℓ は必ず D_v に支配される。したがって v の生存範囲は支配木の部分木をなす。
補題: v と w が点 ℓ で同時生存なら、D_v と D_w のいずれかが他方を支配する（両方 ℓ を支配するため、支配関係は ℓ 上で全順序）。
定理: 支配木の部分木族の交差グラフは弦グラフ（Gavril/Buneman/Walter）。ゆえに干渉グラフは弦。
系: 支配木の後行順が PEO を与えるので、その逆順の貪欲彩ごうで χ(G) = ω(G) = MaxLive（同時生存変数数の最大値）色が線形〜O(n²) 時間で達成される。すなわち「k レジスタで足りるか」は MaxLive ≤ k の判定に帰着する。
φ 関数の扱い（φ の引数は先行ブロックの末尾で「並列に」消費されるという解釈）が本質的で、この解釈を採らないと弦性は崩れます。

重要な注意（実務・理論とも）
弦性は「彩色が易しい」ことしか言いません。レジスタ割当全体が多項式時間になるわけではない点は、以下の一次資料が明確にしています。
F. M. Q. Pereira, J. Palsberg, “Register Allocation After Classical SSA Elimination is NP-Complete,” FoSSaCS 2006, LNCS 3921. — SSA で彩色してから古典的な φ 除去（φ をコピー命令に置換）をすると、レジスタ割当は NP 完全に戻る（circular-arc graph 彩色からの帰着）。
F. Bouchez, A. Darte, F. Rastello, C. Guillon, “Register Allocation: What Does the NP-Completeness Proof of Chaitin et al. Really Prove?” LCPC 2006 / WDDD’06. — Chaitin らの NP 完全性の源泉は彩色ではなく、critical edge の存在・spill コスト最適化・coalescing コスト最適化の 3 つにあると分析。critical edge を分割でき、レジスタ swap が使えるなら「k レジスタで足りるか」は MaxLive ≤ k で判定でき、原理的に易しい、と示しています。
coalescing は SSA 上でも NP 完全（Bouchez et al., On the Complexity of Register Coalescing, RR2006-15, LIP ENS-Lyon, 2006）。
spilling も NP 完全（Bouchez, Darte, Rastello, On the Complexity of Spill Everywhere under SSA Form, LCTES 2007; arXiv:0710.3642）。

解説・教科書
F. Rastello, F. Bouchez Tichadou (eds.), SSA-based Compiler Design, Springer, 2022（ドラフトは 2011 年頃から公開）。Hack 執筆の “Register Allocation” 章が、支配木＝部分木＝弦グラフの議論を最も読みやすくまとめています。SSA 全般の標準リファレンス。
Hack の博士論文（2007） の第 4 章 — 証明が最も丁寧。
M. C. Golumbic, Algorithmic Graph Theory and Perfect Graphs, Academic Press, 1980, Theorem 4.8 — 部分木交差表現の定理。Bouchez らが「この定理を知っていれば自明」と指した箇所そのものです。
応用の拡張例として P. Brisk, A. K. Verma, P. Ienne, “An Optimal Linear-Time Algorithm for Interprocedural Register Allocation in High Level Synthesis Using SSA Form,” IEEE TCAD 29(7):1096–1109, 2010 — 手続き間干渉グラフは SSA 化しても弦とは限らないため、SSA-LLP という拡張で弦性を回復させる、という論文。
もし「最初の一本だけ読む」なら Hack & Goos, IPL 98(4):150–155, 2006 が 6 ページで支配木→PEO→最適彩色まで完結しており、並行計算の文脈から入る方にも読みやすいと思います。
User
SSAの文脈におけるcoalescingの正確な定義は何ですか？
Claude
一言で言うと
coalescing とは、コピー命令（b = a、および φ 関数の各引数と結果のペア）で結ばれた 2 つの変数に同じレジスタを割り当てることで、そのコピー命令を消去する操作です。SSA の文脈では、これを「干渉グラフの頂点の融合」ではなく「アフィニティ付き彩色問題」として定式化するのが正確です。以下、段階的に定式化します。

1. 古典的（Chaitin 流）の定義
G. J. Chaitin, “Register Allocation & Spilling via Graph Coloring,” CC 1982, SIGPLAN Notices 17(6):98–105 が原典です。
干渉グラフ G = (V, E) とコピー命令 b = a が与えられたとき、{a, b} ∉ E（a と b が干渉しない）ならば、頂点 a と b を 1 つの頂点 ab に融合 (merge) し、N(ab) = N(a) ∪ N(b) とする。この融合を行うと a と b は必ず同じレジスタを得るので、コピー命令は不要になる。
形式的には、V 上の同値関係 ≡ による商グラフ G/≡ を考える操作です。
妥当性条件: 各同値類が G の独立集合であること（同じクラスに干渉する 2 変数が入ってはならない）。
G/≡ の辺: [u][v] ∈ E(G/≡) ⟺ ∃u’ ∈ [u], v’ ∈ [v] で {u’, v’} ∈ E。
問題は、融合により頂点次数が増え、彩色数 χ が増加しうることです。これが SSA 文脈で決定的に重要になります。

2. SSA 文脈での正確な定式化：アフィニティ彩色
Hack らの枠組み（S. Hack, D. Grund, G. Goos, “Register Allocation for Programs in SSA-Form,” CC 2006, LNCS 3923, pp. 247–262）では、coalescing は「融合」ではなく彩色の目的関数として定義されます。
与えられるもの：
干渉グラフ G = (V, E)（SSA なので弦グラフ、χ(G) = ω(G) = MaxLive）
アフィニティグラフ（affinity graph / move graph） A ⊆ V × V — コピー命令および φ 関数が誘導する頂点対の集合
重み w : A → ℝ≥0 — そのコピーの実行頻度推定（削除できたときの利得）
レジスタ数 k
定義（最適 coalescing）:
G の k 彩色 c : V → {1, …, k} であって、
　　Σ_{(u,v) ∈ A, c(u) = c(v)} w(u, v)
を最大化するものを求める問題。
等価に「Σ_{(u,v) ∈ A, c(u) ≠ c(v)} w(u,v) を最小化する」＝残るコピー命令の総コストを最小化する問題です。
この定式化が SSA では本質的です。理由は、干渉グラフが弦であるおかげで「k 彩色可能か」は MaxLive ≤ k で即座に決まるため、coalescing は実行可能性の問題ではなく純粋な最適化問題として分離できるからです。Hack らの CC 2006 の主張「coloring / spilling / coalescing を完全に decouple できる」はこの意味です。
なお注意点として、融合は弦性を壊します。Hack らの CC 2006 の Figure 1 は、χ(G) = 2 のプログラムに対して aggressive な coalescing を行うと彩色数が増えてしまう例を挙げており、「coalescing は害をなしうる」と明記しています。融合後のグラフはもはや弦ではないので、その k 彩色可能性判定は一般に NP 困難に戻ります。

3. 4 つの変種（この分類が事実上の標準）
一次資料は F. Bouchez, A. Darte, F. Rastello, “On the Complexity of Register Coalescing,” CGO 2007, pp. 102–114（先行版: Technical Report RR2006-15, LIP, ENS-Lyon, April 2006）です。ここで 4 つが厳密に定義され、すべて NP 完全であることが示されています。
名称
定義
aggressive coalescing
k 彩色可能性を無視し、重みの総和が最大になるようにアフィニティ辺を融合する。結果が k 彩色不能になりうる。
conservative coalescing
「融合後のグラフが依然として k 彩色可能である」という制約の下で、重みの総和を最大化する。
incremental conservative coalescing
アフィニティ辺を 1 本ずつ、k 彩色可能性を保つ限りにおいて融合していく（貪欲・逐次版）。
optimistic coalescing
まず aggressive に融合し、彩色に失敗したら融合を部分的に解く (de-coalescing / splitting back)。原典は J. Park, S.-M. Moon, “Optimistic Register Coalescing,” PACT 1998, pp. 196–204（TOPLAS 26(4):735–765, 2004）。
実装上の代表例が L. George, A. W. Appel, “Iterated Register Coalescing,” ACM TOPLAS 18(3):300–324, 1996 の conservative な安全条件（Briggs 条件: 融合後の頂点で次数 ≥ k の隣接点が k 個未満／George 条件: a の各隣接点が b と干渉するか次数 < k）です。これらは「彩色可能性を保つための十分条件」であり、定義そのものではない点に注意してください。

4. SSA 固有の論点
(a) φ 関数の扱い
φ 関数は「先行ブロック末尾での並列コピー」と解釈されます。したがって SSA における coalescing の主対象は
明示的な b = a 形のコピー
φ 関数 x₀ = φ(x₁, …, xₙ) が誘導するアフィニティ対 (x₀, xᵢ)（i = 1..n）
の両方です。φ に対応するアフィニティをすべて融合できれば、out-of-SSA 変換でコピー命令が一切挿入されません。
この観点の定式化として V. C. Sreedhar, R. D.-C. Ju, D. M. Gillies, V. Santhanam, “Translating Out of Static Single Assignment Form,” SAS 1999, LNCS 1694, pp. 194–210 の φ-congruence class（φ で結ばれた変数の同値類）と CSSA (Conventional SSA)（各 φ-congruence class が独立集合である SSA）の概念が一次資料です。「out-of-SSA = φ-congruence class を独立集合にした上で各クラスを 1 レジスタに割り当てる」という見方は、まさに coalescing の定義そのものです。
(b) coalescing は splitting の逆操作
Bouchez らの整理では、レジスタ割当を「splitting（move の挿入）」と「coalescing（move の除去）」の対として捉えます。SSA 化そのものが極端な live-range splitting なので、SSA-based register allocation における coalescing は「SSA が入れすぎた分割をどこまで戻すか」を決める問題である、という位置づけになります。
(c) 干渉の定義に依存する
「coalescing 可能 ⟺ 干渉しない」という条件は、干渉の定義に依存します。
同時生存 (simultaneously live) による定義 — strict SSA での弦性の証明はこちらを使います。
Chaitin の定義 — v と w が干渉するのは、一方が他方の定義点で生存しているとき。strict なプログラムでは両者は一致します（Bouchez らの脚注で明示）。
値ベースの干渉 (value-based interference) — 同じ値を保持する 2 変数は「干渉しない」とみなす拡張。Z. Budimlić, K. Cooper, T. Harvey, K. Kennedy, T. Oberg, S. Reeves, “Fast Copy Coalescing and Live-Range Identification,” PLDI 2002, pp. 25–32 が原典で、コピーで結ばれた変数は定義上同値なので、通常の干渉判定より多くの融合が可能になります。

5. 最適解法と解説
D. Grund, S. Hack, “A Fast Cutting-Plane Algorithm for Optimal Coalescing,” CC 2007, LNCS 4420, pp. 111–125 — 上記 §2 のアフィニティ彩色を ILP として厳密に解く。定式化が最も明示的に書かれている文献です。
S. Hack, “Register Allocation for Programs in SSA Form,” Ph.D. thesis, Universität Karlsruhe, 2007 — 第 5 章が coalescing。
F. Rastello, F. Bouchez Tichadou (eds.), SSA-based Compiler Design, Springer, 2022 — “Register Allocation” 章および “Out-of-SSA Translation” 章。定義の整理としては現在最も読みやすい二次資料です。
F. Bouchez, A. Darte, F. Rastello, “Advanced Conservative and Optimistic Register Coalescing,” CASES 2008, pp. 147–156 — 実用ヒューリスティクスの比較。
まとめると、SSA 文脈での厳密な定義は 「アフィニティグラフ A と重み w が付随した弦グラフ G に対し、同色アフィニティ辺の重み和を最大化する k 彩色を求める問題」 であり、古典的な「頂点融合」はその近似的な実装手段にすぎない、と理解するのが正確です。
