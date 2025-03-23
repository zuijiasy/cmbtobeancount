# 招商银行账单转Beancount工具

这是一个将招商银行账单转换为Beancount格式的Python工具。

## 功能特点

- 支持导入招商银行的账单pdf文件
- 自动解析交易日期、金额、描述等信息
- 生成符合Beancount格式的文本输出
- 智能匹配和分类交易类别
- 支持自定义账户映射

## 使用方法

1. 准备招商银行的账单pdf文件
2. 运行转换程序：
   ```bash
   python cmb2beancount.py input.pdf output.bean
   ```
3. 查看生成的Beancount文件

## 依赖要求

- Python 3.8+
- pandas
- python-dateutil

## 安装

```bash
pip install -r requirements.txt
```

## 配置说明

在`config.yaml`中可以配置：
- 默认货币
- 账户映射规则
- 商家分类规则
- 导入账户信息

## 注意事项

- 建议在导入前备份原始账单文件
- 首次使用时请检查生成的账单是否正确 
