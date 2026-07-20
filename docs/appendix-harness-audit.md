# Appendix: line-by-line audit of nine open-source "LLM plays Pokémon" harnesses

Companion to the main article. The article keeps only the conclusion — *"vision-only" is mostly a marketing term* — and this appendix is the evidence: for each repo, what the model **actually** receives in its user message, established by reading the input-assembly code (not the README).

Audit method: for each project, locate the function that builds the request sent to the model, and enumerate every content block. A project is "vision-only" only if the model's input is the screenshot (and the model's own notes) and nothing else — no RAM-derived text, no coordinate/grid overlay, no injected walkthrough.

## The nine repos

| Project | Claims | What the model actually receives |
|---|---|---|
| [LLM-Pokemon-Red](https://github.com/martoast/LLM-Pokemon-Red) | "only seeing the game screen, just like a human would" | Player X/Y coordinates, facing direction, and map ID read from emulator RAM via a Lua hook, injected as text every turn; the prompt also hard-codes the naming-screen keyboard layout and walkthrough knowledge like "red carpets/doors/stairs are exits" |
| [PokemonLLMAgentBenchmark](https://github.com/CalebDeLeeuwMisfits/PokemonLLMAgentBenchmark) | vision agent benchmark | A full RAM toolkit (coordinates/party/badges) + OCR + OpenCV dialog detection; the screenshot is passed as a code variable into an execution environment and never enters the model as an image block — one of the default models is text-only |
| [claude-plays-pokemon](https://github.com/roman01la/claude-plays-pokemon) | weekend demo | The only genuinely vision-only harness of the nine — but the purity is an architectural byproduct (the emulator is a black-box process; internal state is physically unreachable), and there is no memory mechanism at all: a hard 100-turn cap |
| [ClaudePlayer](https://github.com/jmurth1234/ClaudePlayer) | general Game Boy agent | Mostly pure by default; but `ENABLE_WRAPPER=true` appends a tile-based text map. Heaviest memory engineering of the group: sliding-window history + 4 structured memory CRUD tools + a three-part summary every 30 turns |
| [ClaudePlaysPokemonStarter](https://github.com/davidhershey/ClaudePlaysPokemonStarter) (Anthropic's official starter) | minimal teaching version | Full RAM state text: money, badges, inventory, coordinates, party stats, four-direction walkability — even dialog text is read straight from the screen character buffer, i.e. free perfect OCR; plus an A\* navigation tool, off by default |
| [llm_pokemon_scaffold](https://github.com/cicero225/llm_pokemon_scaffold) | "to see just what is necessary" | 4× upscaled screenshots with a red grid and per-tile text labels, RAM state text, the last 40 coordinates, a persistent ASCII collision map with BFS distance fields, cross-screen auto-pathing, a dedicated navigator sub-model, and a three-stage "Meta-Critic" memory-cleaning pipeline |
| [pokemon-agent](https://github.com/NousResearch/pokemon-agent) (Nous Research) | industrial infrastructure | Screenshots with an A1..J9 label grid and red/green walkability tinting, compact JSON state (coordinates/money/badges/full party/battle data), an ASCII walkability map, semantic action macros ("press A until dialog ends"); the prompt injects a full type chart and a 17-item completion checklist |
| [videogamebench](https://github.com/alexzhang13/videogamebench) (Princeton; the academic baseline) | raw screenshots + buttons | The input side really is screenshots only; but the per-game prompt is stuffed with walkthrough tips (type chart, "red-roofed buildings are Pokémon Centers") — and the Crystal prompt was copied from Red and never fixed (it still talks about Pallet Town and a 151-entry Pokédex); the paper's Crystal numbers were produced under that configuration |
| [continual-harness](https://github.com/sethkarten/continual-harness) (Princeton; the official NeurIPS PokéAgent framework) | has a "vision_only" mode | Even that mode has four non-visual leaks: human-curated objective sequences (with navigation hints), RAM location mixed into the reflection context, a Bulbapedia lookup tool, and an optional walkthrough; the paper's "minimalist" condition always includes an ASCII collision map, and no truly vision-only condition was evaluated |

## Beyond the repos: the livestream projects

The three long-running livestream projects are the source of most "completed the game" records, and their harnesses are just as thick:

- **[Claude Plays Pokémon](https://www.twitch.tv/claudeplayspokemon)** (Anthropic's official stream): a knowledge base, a critic model, a coordinate-constrained navigator, key RAM data, and screenshot overlays — with a zoom tool and screenshot storage added in the Opus 4.7 era.
- **[Gemini Plays Pokémon](https://blog.jcz.dev/the-making-of-gemini-plays-pokemon)** (independent developer Joel Z): the thickest in the ecosystem — fog-of-war minimap, a dedicated BFS pathfinding agent, a boulder-puzzle agent, and letting the model write code to generate paths. Its author explicitly asks readers: "Please don't consider this a benchmark for how well an LLM can play Pokémon" — because "direct model-to-model comparisons are tricky when the scaffolding around them differs."
- **[GPT Plays Pokémon](https://gpt-plays-pokemon.clad3815.dev/crystal/harness)** (independent developer Clad3815): extracts state via the game's decompilation project plus long-range pathfinding — the most step-efficient in the ecosystem (GPT-5 finished Red in 6,470 steps), but heavily RAM-dependent.

## Why they are all thick — and why that is the point

The thickness is not laziness; every layer is a rational compensation for a known model deficit. The author of `llm_pokemon_scaffold` published the ecosystem's most honest per-component efficacy review in his [research notes on LessWrong](https://www.lesswrong.com/posts/8aPyKyRrMAQatFSnG). In his own words: the grid coordinate labels suppressed the problem that "Claude was awful at using the navigation tool because he simply didn't know what tile was which"; walkability tinting "*mitigates* it, but doesn't entirely eliminate it"; the navigation tool "ends up being mostly QoL for human observers"; and letting the model draw its own ASCII map was "a total loss and probably hurts more than helps." His opening assessment: LLM performance on Pokémon Red is "*highly* dependent on the scaffold and tooling provided." Nous wrote the same philosophy into their agent's skill file (`skill/SKILL.md`): "They complement each other — RAM gives geometry, vision gives meaning," and "The single biggest mistake an agent makes is guessing walkability from raw pixels and getting lost."

That is the ecosystem's engineering consensus: VLM spatial vision is unreliable, so the geometry gets backstopped with coordinates read from memory. Which is exactly why a genuinely thin, vision-only harness is worth running — it is the only configuration that measures the model instead of the scaffolding.

---

# 附录：九个开源“AI 玩宝可梦”harness 的逐行审计（中文）

正文只保留了结论——**“纯视觉”在这个圈子里基本是营销**——这份附录是它的证据：逐个仓库列出模型每 turn **实际**收到什么，依据是读输入组装代码（不是读 README）。

审计方法：对每个项目，定位组装“发给模型的请求”的那个函数，枚举它的每一个 content block。只有当模型输入是截图（加模型自己的笔记）、别无他物时，才算“纯视觉”——不含任何 RAM 派生文本、不含坐标/网格叠加、不含注入的攻略。

## 九个仓库

| 项目 | 自称 | 模型实际收到的东西 |
|---|---|---|
| [LLM-Pokemon-Red](https://github.com/martoast/LLM-Pokemon-Red) | “only seeing the game screen, just like a human would” | Lua 钩子从模拟器 RAM 读出玩家 X/Y 坐标、朝向、地图 ID，每 turn 以文本注入；prompt 里还硬编码了起名键盘布局和“红地毯/门/楼梯是出口”这类攻略知识 |
| [PokemonLLMAgentBenchmark](https://github.com/CalebDeLeeuwMisfits/PokemonLLMAgentBenchmark) | 视觉 agent benchmark | RAM 读取全家桶（坐标/队伍/徽章）+ OCR + OpenCV 对话框检测；截图只作为代码变量传进执行环境，从未以图像块进入模型——默认模型之一甚至是纯文本代码模型 |
| [claude-plays-pokemon](https://github.com/roman01la/claude-plays-pokemon) | 周末 demo | 九个仓库里唯一的真·纯视觉——但纯度是架构副产品（模拟器是黑盒进程，物理上拿不到内部状态），且没有任何记忆机制，100 turn 硬停 |
| [ClaudePlayer](https://github.com/jmurth1234/ClaudePlayer) | 通用 Game Boy agent | 默认输入基本纯；但 `ENABLE_WRAPPER=true` 一开就追加 tile 文字地图。记忆工程最重：滑窗历史+结构化 memory CRUD 工具×4+每 30 turn 三段摘要 |
| [ClaudePlaysPokemonStarter](https://github.com/davidhershey/ClaudePlaysPokemonStarter)（Anthropic 官方 starter） | 极简教学版 | 完整 RAM 状态文本：金钱、徽章、背包、坐标、队伍数据、四方向可走性——连对话文字都直接从屏幕字符缓冲区读取，等于免费的完美 OCR；另带一个默认关闭的 A* 导航工具 |
| [llm_pokemon_scaffold](https://github.com/cicero225/llm_pokemon_scaffold) | “看看到底需要什么” | 4 倍放大+红网格+每格写字的重标注截图、RAM 状态文本、最近 40 步坐标历史、持久 ASCII 碰撞地图（带 BFS 距离场）、跨屏自动寻路、独立 navigator 子模型、三段式 Meta-Critic 记忆清洗 |
| [pokemon-agent](https://github.com/NousResearch/pokemon-agent)（Nous Research） | 工业级基础设施 | A1..J9 标签网格+红绿通行性染色的截图、紧凑 JSON 状态（坐标/金钱/徽章/全队/战斗数据）、ASCII 通行地图、语义动作宏（如“连按 A 直到对话结束”）；prompt 注入完整属性克制表和 17 项通关里程碑 |
| [videogamebench](https://github.com/alexzhang13/videogamebench)（Princeton，学术基线） | 纯截图+按键 | 输入端确实只有截图；但游戏专属 prompt 塞满攻略 tips（属性克制表、“红顶建筑是宝可梦中心”）——且 Crystal 的 prompt 从 Red 复制后未改（仍写着真新镇与 151 只图鉴），其论文成绩系在该配置下取得 |
| [continual-harness](https://github.com/sethkarten/continual-harness)（Princeton，NeurIPS PokéAgent 官方框架） | 有 “vision_only” 档 | 连该档都有 4 处非视觉泄漏：人工策划的目标序列（含导航提示）、反思上下文混入 RAM 位置、Bulbapedia 攻略工具、可选 walkthrough；其论文的 “minimalist” 条件必含 ASCII 碰撞地图，且论文没有评测任何真正 vision-only 的条件 |

## 开源仓库之外：三个直播项目

这个生态大多数“通关”战绩来自三个长期直播项目，它们的 harness 同样是厚的：

- **[Claude Plays Pokémon](https://www.twitch.tv/claudeplayspokemon)**（Anthropic 官方直播）：knowledge base、critic 模型、带坐标约束的 navigator、关键 RAM 数据、截图 overlay——Opus 4.7 时代又加了 zoom 工具和截图存储。
- **[Gemini Plays Pokémon](https://blog.jcz.dev/the-making-of-gemini-plays-pokemon)**（独立开发者 Joel Z）：全生态最厚——fog-of-war minimap、专职 BFS 寻路 agent、推箱子解谜 agent、让模型写代码生成路径。作者本人明确请求读者：“Please don't consider this a benchmark for how well an LLM can play Pokémon”（请不要把它当作衡量 LLM 玩宝可梦水平的 benchmark）——因为“direct model-to-model comparisons are tricky when the scaffolding around them differs”（脚手架不同时，模型之间很难直接对比）。
- **[GPT Plays Pokémon](https://gpt-plays-pokemon.clad3815.dev/crystal/harness)**（独立开发者 Clad3815）：基于游戏反编译工程做 RAM 状态提取加长距离寻路——步数效率全生态第一（GPT-5 通关 Red 只用 6,470 步），但同样重度依赖 RAM。

## 为什么它们都这么厚——以及这为什么恰恰是重点

厚不是偷懒，每一层都是对模型某个已知短板的理性补偿。`llm_pokemon_scaffold` 的作者在 [LessWrong 的实验笔记](https://www.lesswrong.com/posts/8aPyKyRrMAQatFSnG)里给过全生态最坦诚的组件疗效自评，用他自己的原话：网格坐标标注压制的是“Claude was awful at using the navigation tool because he simply didn't know what tile was which”（Claude 根本不知道哪块 tile 是哪块）这个问题；通行性染色“*mitigates* it, but doesn't entirely eliminate it”（缓解但没根除）；导航工具“ends up being mostly QoL for human observers”（最后主要是给人类观众提速的生活质量改善）；让模型自己画 ASCII 地图则是“a total loss and probably hurts more than helps”（彻底失败，可能弊大于利）。他的开篇判断：LLM 在红版上的表现“*highly* dependent on the scaffold and tooling provided”（高度依赖所提供的脚手架与工具）。Nous 把同一套哲学写进了 agent 的技能文件（`skill/SKILL.md`）：“They complement each other — RAM gives geometry, vision gives meaning.”（两者互补——RAM 给几何，视觉给语义）以及“The single biggest mistake an agent makes is guessing walkability from raw pixels and getting lost.”（agent 犯的最大错误，就是从原始像素猜可走性然后迷路）。

这就是整个生态的工程共识：VLM 的空间视觉不可靠，所以几何要用内存里读出的坐标托底。而这恰恰是"跑一个真正薄的、纯视觉 harness"值得做的原因——它是唯一一种测的是模型、而不是脚手架的配置。
