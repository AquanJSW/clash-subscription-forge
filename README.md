# Clash Subscription Forge

## 特性

- 过滤无效节点（无法连通的节点）
- 过滤重复节点（服务器两侧的IP均相同）
- 合并订阅

## 例子

```bash
#!/usr/bin/env bash
subs=(
    'http://subscripton-example-1/config.yaml'
    'http://subscripton-example-2/config.yaml'
)
patterns=(
    '更新订阅'
    '最新网址'
)
templateConfigs=(
    '/path/to/template-1.yaml'
)
outputConfigs=(
    '/path/to/output-1.yaml'
)

./main.py -s "${subs[@]}" -t "${templateConfigs[@]}" -c -o "${outputConfigs[@]}" -p "${patterns[@]}"
```
过滤效果也可在日志中查看：
```
...
[INFO] change of subscription-example-1: 40 -> 13
[INFO] change of subscription-example-2: 14 -> 11
...
```