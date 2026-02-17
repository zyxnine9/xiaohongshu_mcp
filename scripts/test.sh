# 运行全部测试
python scripts/test_xiaohongshu.py

# 只测试登录
python scripts/test_xiaohongshu.py --test login

# 只测试搜索
python scripts/test_xiaohongshu.py --test search --keyword 旅游 --limit 10

# 只测试读取评论（自动从搜索获取一条笔记）
python scripts/test_xiaohongshu.py --test comments

# 指定笔记 ID 测试评论
python scripts/test_xiaohongshu.py --test comments --post-id 你的笔记ID

# 显示浏览器窗口（调试用）
python scripts/test_xiaohongshu.py --no-headless