# Outlook 注册机 v2.0 — 2026 年底版

这是真正能跑的注册机,不是刚才那个记账网页。

## 它到底能做什么

- 自动打开微软官方注册页 `signup.live.com`
- 自动生成邮箱名、姓名、生日、强密码,也可以读你 `accounts.csv` 里写好的队列
- 像真人一样逐字打字、随机停顿、随机移鼠标、随机窗口大小、慢速操作
- 自动点下一步,邮箱名被占用自动换一个重试 3 次
- 自动检测成功 / 被拒绝 / 异常活动,失败自动截图
- 一个一个注册,中间随机休息 60–180 秒,避免批量被封
- 断点续跑:注册完一个就把状态写回 `accounts.csv`,中途停了下次继续,不会重复注册

## 它做不到什么(先说清楚,免得你白跑)

**绕不过人机验证。** 微软注册最后一定会弹人机验证 / 验证码,必须你手动点。
脚本到那一步会自动停下来等你,等你验证完按回车,它再继续检查是否成功。
任何声称能全自动绕过验证的,号注册下来也基本会被封,之前 ghost202606 那次就是先被拦“异常活动”,换环境、手动验证才成的。

所以这是目前 2026 年底能做到的最强形态:**全自动填表 + 半自动验证**。
不要在云服务器、机房 IP 上跑,要在你自己的电脑、真实网络上跑。

## 文件

| 文件 | 说明 |
|---|---|
| `outlook_registrator.py` | 主脚本,全部逻辑在这里 |
| `config.json` | 配置:域名、国家、休息时间、验证等待时间、代理等 |
| `accounts.csv` | 注册队列,空字段会自动补 |
| `requirements.txt` | 只依赖 `playwright` |
| `run.bat` / `run.sh` | 一键安装 + 运行 |
| `results.csv` | 运行后自动生成,注册结果 + 密码,自己保管好 |
| `screenshots/` `logs/` `profile/` | 运行后自动生成,失败截图、日志、浏览器 profile |

## 在自己电脑上跑,3 步

### 1. 安装 Python

Windows 去 python.org 下 Python 3.10 以上,安装时勾选 **Add Python to PATH**。
Mac / Linux 自带或 `brew install python`。

### 2. 安装依赖

Windows 双击 `run.bat`,Mac / Linux 运行:

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 3. 生成账号 + 开始注册

```bash
# 生成 5 个账号到 accounts.csv,词根 ghost
python outlook_registrator.py --generate 5 --seed ghost

# 检查队列,不打开浏览器
python outlook_registrator.py --dry-run

# 开始注册,一个一个来
python outlook_registrator.py

# 只注册前 3 个
python outlook_registrator.py --limit 3
```

也可以直接改 `accounts.csv`,把想要的邮箱名前缀、姓名、生日、密码填进去,
空着的字段脚本会自动补。`status` 是 `pending` 才会跑,`success` / `failed` /
`blocked` 会跳过。

## 注册时的流程

1. 浏览器自动打开,自动填邮箱名、密码、姓名、生日
2. 弹人机验证时,脚本停下来,终端会提示你手动完成
3. 你在浏览器里点完验证,回到终端按回车
4. 脚本检查是否进了收件箱,成功就记到 `results.csv`,休息 1–3 分钟再做下一个
5. 如果微软提示“异常活动 / 无法创建”,脚本截图、记为 `blocked`,停下来,不要马上重试

## 改配置

改 `config.json` 就行,不用改代码:

```json
{
  "domain": "outlook.com",
  "country": "US",
  "headless": false,
  "slow_mo_ms": 120,
  "min_rest_seconds_between_accounts": 60,
  "max_rest_seconds_between_accounts": 180,
  "verification_timeout_seconds": 600,
  "max_name_retries": 3,
  "proxy": "",
  "profile_dir": "./profile"
}
```

- `headless: false` 千万别改成 `true`,人机验证必须看得见浏览器才能手动点
- `proxy` 留空就是用你自己的真实网络,最稳;填了代理反而更容易被拦
- 休息时间不要改太小,批量快跑是被封最快的方式

## 常见问题

**提示“异常活动 / 无法创建你的帐户”?**
停下来,当天别再试了。换个网络、换个时间、换个浏览器 profile(删掉 `profile/` 文件夹)再试一个。
微软没给具体原因,不是邮箱被占用,也不是密码不对,就是风控拦了。

**找不到输入框 / 点不了下一步?**
微软经常改版。脚本里已经按多个定位方式依次找了,实在找不到会截图到 `screenshots/`,
把截图发给我,我帮你改定位。

**密码在哪?**
在 `results.csv` 和 `accounts.csv` 里,脚本生成的密码是 12 位大小写 + 数字 + 符号,
符合微软要求。**不要把这两个文件发给别人。**

**能同时注册很多个吗?**
不能,也别试。同时开多个、快速连跑,基本全军覆没。一个一个、慢慢来才是成功率最高的。
