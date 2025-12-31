import requests
import json

url = "https://www.dmxapi.cn/v1/chat/completions"
headers = {
    'Accept': 'application/json',
    'Authorization': 'Bearer sk-3zK5hQbruFCZoGo20cmvjpalOJRKSfbYHomFoKY9MQMWp8XZ',
    'Content-Type': 'application/json'
}

payload = json.dumps({
    "model": "gpt-5-nano",
    "messages": [
        {
            "role": "system",
            "content": "You are a helpful assistant."
        },
        {
            "role": "user",
            "content": "我擅长云计算与运维领域，持有 HCIE 云计算、HCIP 数通双认证，数通方向熟悉 TCP/IP 协议、路由交换配置及基础网络故障排查；云计算方向精通 OpenStack 高可用架构、Kubernetes 容器化技术及华为 HCS 平台运维，熟练使用 Ansible 自动化工具、Prometheus+Grafana 监控体系，能开发 Shell 脚本实现自定义监控，掌握 MySQL 集群部署、主从同步、慢查询优化及 Nginx 负载均衡配置，熟练运用 Linux 命令，具备机房设备运维实操能力；拥有 4 个月广州联通信创云驻场经验，负责云资源交付、机房巡检及故障处理，曾独立完成 OpenStack 私有云高可用集群项目，东莞城市学院本科就读软件工程专业，获华为 ICT 大赛及省技能竞赛奖项，专业基础扎实。这是我的专业技能背景描述。我目前在找工作,运维,我期望的的岗位方向是运维,目前我需要投递的岗位名称是运维助理,这个岗位的要求是岗位职责：1. 负责日常运维活动的助理支持，包括但不限于监控系统性能、协助进行系统配置和调试。2. 支持运维团队完成特定的项目或任务，确保工作按时完成。3. 学习和掌握运维相关工具和技术的使用方法，以提高工作效率。4. 参与团队会议，提出改进建议，协助优化运维流程和方法。5. 根据需要进行其他相关工作，以支持团队成员和完成项目目标。任职要求：1. 对运维工作有高度的热情和兴趣，愿意学习新知识。2. 有良好的团队合作精神，能够有效沟通。3. 拥有基本的计算机操作能力和网络知识，能够使用常见的运维工具。4. 有责任心，能够在压力下工作，并确保任务的准确完成。5. 愿意接受挑战，对解决复杂问题充满热情。,如果这个岗位和我的期望与经历基本符合，注意是基本符合，那么请帮我写一个可以直接发给HR打招呼的文本发给我，如果这个岗位和我的期望经历完全不相干，直接返回false给我，注意只要返回我需要的内容即可，不要有其他的语气助词，重点要突出我和岗位的匹配度以及我的优势，我自己写的招呼语是：您好！持有HCIE云计算+HCIP数通认证，有广州联通政务云运维经验，可全职实习，看到贵司岗位，非常匹配，盼回复！,你可以参照我自己写的根据岗位情况进行适当调整"
        }
    ]
})

response = requests.post(url, headers=headers, data=payload)
response_json = response.json()

# 提取并打印AI回复的内容（忽略JSON格式，直接显示文字）
try:
    reply = response_json['choices'][0]['message']['content']
    print("BOSS直聘打招呼话术：")
    print("-" * 50)
    print(reply)
    print("-" * 50)
except KeyError:
    # 如果API返回格式异常，打印错误信息
    print("获取回复失败：", response_json)