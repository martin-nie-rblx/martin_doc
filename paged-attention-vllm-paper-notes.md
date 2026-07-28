# PagedAttention 与 vLLM 论文解读

论文：*Efficient Memory Management for Large Language Model Serving with PagedAttention*  
作者：Woosuk Kwon 等  
会议：SOSP 2023  
链接：https://arxiv.org/abs/2309.06180

## 一句话总结

这篇论文把大模型在线推理中的 KV cache 当作操作系统管理的虚拟内存：用固定大小的块进行按需分配，通过块表支持非连续存储，并用引用计数和写时复制共享公共前缀。基于这一机制构建的 vLLM 能让更多请求同时驻留 GPU，从而用更大的动态 batch 提高吞吐。

## 1. 论文解决了什么问题

LLM 的自回归解码一次只生成一个 token。为了生成下一个 token，模型需要读取此前所有 token 在每一层产生的 Key 和 Value。服务系统会把这些状态保存为 KV cache，避免重复计算。

KV cache 有三个重要特征：

1. 它很大。论文以 OPT-13B 为例，每个 token 的 KV cache 约为 800 KB，一条 2048-token 序列最多需要约 1.6 GB。
2. 它动态增长。每生成一个 token，KV cache 都会增加。
3. 最终长度事先未知。请求可能很快结束，也可能一直生成到最大长度。

旧系统通常要求每条序列的 KV cache 在显存中连续，因此会按最大可能长度提前预留一整块空间。这产生三类浪费：

- 预留空间：将来可能使用，但在当前不能给其他请求使用。
- 内部碎片：请求提前结束，预留块尾部永久未用。
- 外部碎片：不同大小连续内存块之间留下难以利用的空洞。

论文的 profiling 显示，旧系统中真正用于保存 token 状态的显存比例可能只有 20.4%–38.2%。显存利用率低会直接限制 batch size，而自回归 decode 本身又是 memory-bound、GPU 利用率偏低的阶段，所以 batch 不够大会显著压低吞吐。

## 2. PagedAttention 的核心设计

PagedAttention 借用了操作系统虚拟内存的抽象：

| LLM serving | 操作系统 |
| --- | --- |
| token 状态 | 字节 |
| KV block | 页 |
| sequence | 进程 |
| block table | 页表 |

每条序列在逻辑上仍拥有连续的 KV cache，但系统把它切成固定 token 数的逻辑块。块表把逻辑块映射到 GPU 中任意位置的物理块，因此相邻逻辑块不必物理连续。

这样做带来三项直接收益：

- 按需分配：不再为最大长度提前占满显存，只在需要时增加新块。
- 消除外部碎片：所有物理块大小一致。
- 限制内部碎片：一条序列只有最后一个块可能未填满，因此浪费至多一个块。

代价是 attention kernel 不能再假设 K/V 张量物理连续。它必须根据块表找到每个物理块，分别读取并完成 attention 计算。论文为此实现了定制 CUDA kernel，并融合了块写入、块读取与 attention、批量块复制等操作。

## 3. 为什么“分页”还能支持共享

块表把“序列看到的逻辑 KV cache”与“实际物理存储”分离后，多条序列可以把自己的逻辑块映射到同一物理块。

### 并行采样

同一个 prompt 生成多个候选答案时，所有候选在分叉前具有相同的 KV cache。vLLM 只保存一份 prompt 块，并通过引用计数让多个序列共享。

如果某条序列需要写入仍被共享的最后一个块，系统执行块级写时复制：复制该块，再让该序列写自己的副本。复制范围被限制为一个块。

### Beam search

不同 beam 不只共享初始 prompt，还可能动态共享后续生成路径。旧系统通常需要在 beam 变化时复制大量 KV cache；vLLM 只调整块表和引用计数，大部分物理块继续共享。

### 跨请求共享前缀

如果多个请求具有相同 system prompt 或 few-shot 示例，服务商可以预先保留这部分前缀的物理块。新请求直接映射这些块，只需计算用户独有的后缀。

## 4. 调度、抢占与多 GPU

vLLM 使用集中式调度器和 iteration-level scheduling。每轮 decode 后，已完成请求离开 batch，新请求可以加入。

当 GPU 块不足时，vLLM 以 sequence group 为单位整体抢占，提供两种恢复方式：

- Swapping：把 KV block 换到 CPU 内存，稍后传回 GPU。
- Recomputation：丢弃 KV cache，恢复时把 prompt 与已生成 token 合并，通过一次 prefill 重算。

小块会导致大量小型 CPU-GPU 传输，使 swapping 的 PCIe 效率较差；recomputation 对块大小不敏感。论文发现中等块大小下两者端到端表现相近。

对于 tensor parallel，多张 GPU 上的模型 shard 处理相同 token 位置，只保存自己负责的 attention heads。集中式调度器维护统一块表，并在每轮开始时把输入 token 和映射信息广播给 worker。

## 5. 实验结论

论文使用 A100 GPU、OPT-13B/66B/175B 和 LLaMA-13B，按 ShareGPT 与 Alpaca 的输入/输出长度生成请求，并使用泊松过程模拟到达时间。

主要结果：

- 总体上，vLLM 在相近延迟下比 FasterTransformer 和 Orca 提高约 2–4 倍吞吐。
- ShareGPT basic sampling 中，相对不可实现但知道真实输出长度的 Orca Oracle，vLLM 可承受高 1.7–2.7 倍的请求率。
- 相对按最大长度预留的 Orca Max，请求率提升为 2.7–8 倍。
- 并行采样通过共享节省 6.1%–9.8%（Alpaca）或 16.2%–30.5%（ShareGPT）的 KV 显存。
- Beam search 节省 37.6%–55.2%（Alpaca）或 44.3%–66.3%（ShareGPT）的 KV 显存。
- 共享 80-token 的 one-shot 前缀时，吞吐相对 Orca Oracle 提高 1.67 倍；共享 341-token 的 five-shot 前缀时提高 3.58 倍。
- PagedAttention kernel 本身比高度优化的 FasterTransformer attention kernel 慢 20%–26%，但更大的可驻留 batch 让端到端吞吐仍显著更高。
- 块太小会降低 GPU 并行利用率，块太大会增加内部碎片并减少共享机会。论文采用 16 tokens 作为默认块大小。

一个重要边界是：当序列较短、KV cache 显存充足时，系统会从 memory-bound 转为 compute-bound，此时 vLLM 的优势会缩小。

## 6. 如何理解这篇论文的贡献

它的主要创新不是降低 attention 的理论复杂度，也不是让单次 attention 计算更快，而是改变在线服务中 KV cache 的资源管理方式。

PagedAttention 与 FlashAttention 解决不同层面的问题：

- FlashAttention 优化一次 attention 计算内部的数据搬运与片上存储。
- PagedAttention 优化请求生命周期内、跨请求的 KV cache 显存分配和共享。

两者可以互补。

论文最强的地方在于，它把一个成熟的操作系统抽象迁移到新工作负载，并完成了从算法、CUDA kernel、调度、抢占到分布式执行的系统闭环。分页带来的间接寻址并非免费，但只要节省的显存能显著扩大 batch，系统级收益就会超过单个 kernel 的开销。

## 7. 批判性阅读

阅读实验时应保留以下限制：

1. Orca 未开源，论文中的 Orca 基线由作者自行复现，结果可能受到实现质量影响。
2. 请求长度来自真实数据集，但到达时间是按泊松分布合成的，未必覆盖生产流量的突发性与租户异质性。
3. 论文主要使用平均端到端延迟除以输出 token 数作为 normalized latency，对 TTFT、TPOT、p99 和严格 SLO 的展示有限。
4. 具体倍数来自 2023 年的模型、A100 和软件栈，不能原样外推到所有现代模型与硬件。
5. 分页适合“大小动态、生命周期未知且内存受限”的工作负载。对静态张量或 compute-bound 工作负载，间接寻址反而可能只增加开销。

## 结论

这篇论文最重要的洞察是：LLM 在线推理的吞吐瓶颈，不只在矩阵乘法或 attention kernel，也在 KV cache 能否高效地驻留、增长、共享和回收。

vLLM 将 KV cache 从“每个请求独占的一大块连续张量”变成“可分页、可共享、可抢占的系统资源”。这一抽象显著提高显存利用率，使更大的动态 batch 成为可能，并因此成为现代 LLM serving 系统的基础设计之一。
