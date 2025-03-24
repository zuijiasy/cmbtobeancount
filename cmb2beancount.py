#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
招商银行账单转Beancount工具

此模块用于将招商银行的PDF格式账单转换为Beancount格式的记账文本。
支持信用卡账单和储蓄卡账单。
"""

import argparse
from datetime import datetime
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

import pandas as pd
import pdfplumber
import yaml

class CMBTransaction:
    """招商银行交易记录类"""
    
    def __init__(
        self,
        date: datetime,
        description: str,
        amount: float,
        balance: Optional[float] = None,
        transaction_type: str = '支出',
        card_number: Optional[str] = None,
        foreign_amount: Optional[str] = None
    ):
        """
        初始化交易记录
        
        Args:
            date: 交易日期
            description: 交易描述
            amount: 交易金额
            balance: 账户余额（可选）
            transaction_type: 交易类型（收入/支出）
            card_number: 信用卡卡号末四位（可选）
            foreign_amount: 交易地金额（可选）
        """
        self.date = date
        self.description = description
        self.amount = amount
        self.balance = balance
        self.transaction_type = transaction_type
        self.card_number = card_number
        self.foreign_amount = foreign_amount

class CMBBeanConverter:
    """招商银行账单转Beancount转换器"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        初始化转换器
        
        Args:
            config_path: 配置文件路径
        """
        self.config = self._load_config(config_path)
        self.logger = self._setup_logger()
        
    def _load_config(self, config_path: str) -> Dict:
        """
        加载配置文件
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            配置字典
        """
        if not os.path.exists(config_path):
            return self._create_default_config(config_path)
            
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def _create_default_config(self, config_path: str) -> Dict:
        """
        创建默认配置文件
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            默认配置字典
        """
        default_config = {
            'currency': 'CNY',
            'accounts': {
                'assets': 'Liabilities:CN:CMB:CreditCard',  # 信用卡是负债账户
                'expenses': 'Expenses:Unknown',
                'income': 'Income:Unknown',
                'assets_template': 'Liabilities:CN:CMB:CreditCard:{card_number}'
            },
            'rules': {
                'categories': {}
            }
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, allow_unicode=True)
            
        return default_config
    
    def _setup_logger(self) -> logging.Logger:
        """
        设置日志记录器
        
        Returns:
            配置好的日志记录器
        """
        logger = logging.getLogger('cmb2beancount')
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger

    def _extract_text_from_pdf(self, pdf_path: str) -> List[str]:
        """
        从PDF文件中提取文本行
        
        Args:
            pdf_path: PDF文件路径
            
        Returns:
            文本行列表
        """
        lines = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                self.logger.info(f"开始处理PDF文件，共 {len(pdf.pages)} 页")
                
                for page_num, page in enumerate(pdf.pages, 1):
                    self.logger.info(f"正在处理第 {page_num} 页")
                    
                    # 提取页面文本
                    text = page.extract_text()
                    if text:
                        # 按行分割文本
                        page_lines = text.split('\n')
                        # 过滤空行和无用行
                        page_lines = [line.strip() for line in page_lines if line.strip()]
                        # 过滤掉不包含数字的行（可能是表头或其他信息）
                        page_lines = [line for line in page_lines if any(c.isdigit() for c in line)]
                        
                        # 调试输出
                        self.logger.debug(f"第 {page_num} 页原始文本行:")
                        for line in page_lines:
                            self.logger.debug(f"  {line}")
                        
                        lines.extend(page_lines)
                        self.logger.info(f"第 {page_num} 页成功提取 {len(page_lines)} 行文本")
                    else:
                        self.logger.warning(f"第 {page_num} 页未找到文本")
                
            if not lines:
                raise ValueError("未能从PDF中提取到任何文本数据")
                
            return lines
            
        except Exception as e:
            self.logger.error(f"处理PDF文件时发生错误: {str(e)}")
            raise

    def _parse_transaction_line(self, line: str) -> Optional[CMBTransaction]:
        """
        解析单行交易记录
        
        Args:
            line: 文本行
            
        Returns:
            交易记录对象，如果不是交易记录则返回None
        """
        try:
            # 移除多余的空白字符
            line = re.sub(r'\s+', ' ', line.strip())
            
            # 调试输出
            self.logger.debug(f"尝试解析行: {line}")
            
            # 跳过一些特定的非交易行
            skip_keywords = ['账单', '信用卡', '人民币', '美元', '合计', '小计', '币种', '卡号', '交易日', '本期', '上期', '备注']
            if any(keyword in line for keyword in skip_keywords):
                self.logger.debug(f"跳过非交易行: {line}")
                return None
            
            # 尝试匹配还款交易格式（只有记账日）
            # 格式：记账日 商户名称 金额 卡号末四位 交易地金额
            repayment_pattern = r'(\d{2}/\d{2})\s+([^0-9]+?还款[^0-9]*?)\s+([-+]?[\d,.]+)\s+(\d{4})\s+(.*?)(?:\s*$|\s*\(.*\)$)'
            
            # 尝试匹配普通交易格式
            # 格式：交易日 记账日 商户名称 金额 卡号末四位 交易地金额
            normal_pattern = r'(\d{2}/\d{2})\s+(\d{2}/\d{2})\s+([^0-9]+?)\s+([-+]?[\d,.]+)\s+(\d{4})\s+(.*?)(?:\s*$|\s*\(.*\)$)'
            
            # 首先尝试匹配还款交易
            match = re.search(repayment_pattern, line)
            if match:
                self.logger.debug(f"匹配到还款交易格式")
                groups = match.groups()
                self.logger.debug(f"匹配组: {groups}")
                
                # 解析日期（使用记账日）
                trans_date = self._parse_date(groups[0])
                description = groups[1].strip()
                raw_amount = self._clean_amount(groups[2])
                card_number = groups[3]
                foreign_amount = groups[4].strip()
                
                # 创建还款交易记录
                transaction = CMBTransaction(
                    date=trans_date,
                    description=description,
                    amount=abs(raw_amount),
                    transaction_type='还款',
                    card_number=card_number,
                    foreign_amount=foreign_amount
                )
                
                # 保存当前交易记录用于分类
                self._current_transaction = transaction
                
                self.logger.debug(f"成功解析还款交易: {trans_date.strftime('%Y-%m-%d')} {description} {abs(raw_amount)}")
                return transaction
            
            # 如果不是还款交易，尝试匹配普通交易
            match = re.search(normal_pattern, line)
            if match:
                self.logger.debug(f"匹配到普通交易格式")
                groups = match.groups()
                self.logger.debug(f"匹配组: {groups}")
                
                # 解析交易日期（使用交易日而不是记账日）
                trans_date = self._parse_date(groups[0])
                description = groups[2].strip()
                raw_amount = self._clean_amount(groups[3])
                card_number = groups[4]
                foreign_amount = groups[5].strip()
                
                # 判断是否为退款交易
                is_refund = (
                    # 通过描述关键词判断
                    any(keyword in description.lower() for keyword in [
                        '退款', '退货', '冲正', '撤销', '取消', 
                        '返还', '退回', '退付', '退租', '退定'
                    ]) or
                    # 通过交易地金额中的负号或括号判断
                    (foreign_amount and (
                        foreign_amount.startswith('-') or
                        (foreign_amount.startswith('(') and foreign_amount.endswith(')'))
                    ))
                )
                
                # 确定交易类型和金额
                if is_refund:
                    transaction_type = '退款'
                    amount = abs(raw_amount)
                else:
                    transaction_type = '支出' if raw_amount > 0 else '收入'
                    amount = abs(raw_amount)
                
                # 创建交易记录
                transaction = CMBTransaction(
                    date=trans_date,
                    description=description,
                    amount=amount,
                    transaction_type=transaction_type,
                    card_number=card_number,
                    foreign_amount=foreign_amount
                )
                
                # 保存当前交易记录用于分类
                self._current_transaction = transaction
                
                self.logger.debug(f"成功解析交易: {trans_date.strftime('%Y-%m-%d')} {description} {amount} ({transaction_type})")
                return transaction
            
            self.logger.debug(f"未能匹配交易格式: {line}")
            return None
            
        except Exception as e:
            self.logger.debug(f"解析行失败: {line}, 错误: {str(e)}")
            return None

    def _clean_amount(self, amount_str: str) -> float:
        """
        清理并转换金额字符串
        
        Args:
            amount_str: 金额字符串
            
        Returns:
            float类型的金额
        """
        try:
            # 处理空值
            if pd.isna(amount_str) or amount_str.strip() == '':
                return 0.0
            
            # 移除货币符号、空白字符和千位分隔符
            amount_str = re.sub(r'[¥\s,]', '', str(amount_str))
            
            # 处理特殊符号
            amount_str = amount_str.replace('CR', '-')  # 贷记卡收入标记
            amount_str = amount_str.replace('DR', '')   # 借记卡支出标记
            
            # 处理括号（表示负数）
            if amount_str.startswith('(') and amount_str.endswith(')'):
                amount_str = '-' + amount_str[1:-1]
            
            # 调试输出
            self.logger.debug(f"清理金额: {amount_str}")
            
            return float(amount_str)
            
        except ValueError as e:
            self.logger.warning(f"无法解析金额: {amount_str}, 错误: {str(e)}")
            return 0.0

    def _parse_date(self, date_str: str) -> datetime:
        """
        解析日期字符串
        
        Args:
            date_str: 日期字符串
            
        Returns:
            datetime对象
        """
        # 处理空值
        if pd.isna(date_str) or date_str.strip() == '':
            raise ValueError("日期不能为空")
            
        # 清理日期字符串
        date_str = re.sub(r'\s+', '', str(date_str))
        
        # 调试输出
        self.logger.debug(f"解析日期: {date_str}")
        
        # 尝试多种常见的日期格式
        date_formats = [
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%Y年%m月%d日',
            '%Y.%m.%d',
            '%Y%m%d',
            '%m/%d',  # 处理只有月日的情况
            '%m-%d',
            '%m月%d日'
        ]
        
        # 当前年份（用于处理只有月日的情况）
        current_year = datetime.now().year
        
        # 如果是信用卡账单日期格式（MM/DD），使用账单年份
        if re.match(r'\d{2}/\d{2}$', date_str):
            try:
                # 从账单文件名中提取年份
                bill_year = int(os.path.basename(self.current_file).split('年')[0])
                date = datetime.strptime(date_str, '%m/%d')
                return date.replace(year=bill_year)
            except (ValueError, IndexError, AttributeError):
                # 如果无法从文件名获取年份，使用当前年份
                date = datetime.strptime(date_str, '%m/%d')
                return date.replace(year=current_year)
        
        # 尝试其他日期格式
        for fmt in date_formats:
            try:
                if '%Y' not in fmt:
                    # 对于只有月日的格式，添加当前年份
                    date = datetime.strptime(date_str, fmt)
                    return date.replace(year=current_year)
                else:
                    return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        raise ValueError(f"无法解析日期格式: {date_str}")

    def convert_pdf(self, input_file: str, output_file: str) -> None:
        """
        转换PDF文件到Beancount格式
        
        Args:
            input_file: 输入PDF文件路径
            output_file: 输出Beancount文件路径
        """
        try:
            # 保存当前文件路径（用于从文件名获取年份）
            self.current_file = input_file
            
            # 提取PDF中的文本行
            lines = self._extract_text_from_pdf(input_file)
            
            # 解析交易记录
            transactions = []
            for line in lines:
                transaction = self._parse_transaction_line(line)
                if transaction:
                    transactions.append(transaction)
            
            if not transactions:
                raise ValueError("未能解析出任何有效的交易记录")
            
            # 生成Beancount文本
            beancount_text = self._generate_beancount(transactions)
            
            # 写入输出文件
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(beancount_text)
                
            self.logger.info(f"成功将账单转换为Beancount格式并保存到 {output_file}")
            self.logger.info(f"共处理 {len(transactions)} 条交易记录")
            
        except Exception as e:
            self.logger.error(f"转换过程中发生错误: {str(e)}")
            raise

    def _generate_beancount(self, transactions: List[CMBTransaction]) -> str:
        """
        生成Beancount格式文本
        
        Args:
            transactions: 交易记录列表
            
        Returns:
            Beancount格式的文本
        """
        beancount_lines = []
        
        # 添加文件头注释
        beancount_lines.extend([
            "; 由cmb2beancount工具自动生成",
            "; 生成时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "; 注意：中铁网络等交通支出以及酒店、机票等旅游支出如需报销，请手动添加 #报销 标签并修改支出账户为 Assets:Receivable:Reimbursement:可报销",
            ""
        ])
        
        # 收集所有用到的账户
        accounts = set()
        for trans in transactions:
            accounts.add(self._get_account(trans))
        
        
        # 按日期排序交易记录
        transactions.sort(key=lambda x: x.date)
        
        for trans in transactions:
            date_str = trans.date.strftime("%Y-%m-%d")
            amount_str = f"{trans.amount:.2f} {self.config['currency']}"
            
            # 构建交易描述（不再在描述中显示卡号，因为已经在账户名中体现）
            description = trans.description
            if "有限公" in description and "有限公司" not in description:
                description = description.replace("有限公", "有限公司")
            if trans.foreign_amount:
                description += f" ({trans.foreign_amount})"

            # 获取交易分类
            category_account = self._get_category_account(description)
            
            # 构建Beancount交易记录
            if trans.transaction_type == '还款':
                # 还款交易：从Assets:CN:CMB:Checking账户转入
                lines = [
                    f"{date_str} * \"{description}\" #repayment",  # 添加 #还款 标签
                    f"  ; 类型: 信用卡还款",  # 添加注释说明
                    f"  {self._get_account(trans)} {amount_str}",
                    f"  Assets:CCB4914:建设银行4914"
                ]
            elif trans.transaction_type == '退款':
                # 退款交易：添加特殊标记和标签
                lines = [
                    f"{date_str} * \"{description}\" #refund",  # 添加 #退款 标签
                    f"  ; 类型: 退款交易",  # 添加注释说明
                    f"  {self._get_account(trans)} {amount_str}",
                    f"  {category_account} -{amount_str}"
                ]
            else:
                # 检查是否为可能需要报销的交易
                is_reimbursable = any(keyword in description.lower() for keyword in [
                    '中铁网络', '铁路客票', '火车票', '动车', '高铁', '12306',
                    '差旅', '商务', '出差', '机票', '酒店', '住宿', '招待所', '融通'
                ])
                
                if is_reimbursable:
                    # 可报销交易：添加提示注释
                    lines = [
                        f"{date_str} * \"{description}\"",
                        f"  ; 提示: 如需报销请添加 #报销 标签并修改支出账户为 Assets:Receivable:Reimbursement:可报销",
                        f"  {self._get_account(trans)} -{amount_str}",
                        f"  {category_account}"
                    ]
                else:
                    # 普通收支交易
                    lines = [
                        f"{date_str} * \"{description}\"",
                        f"  {self._get_account(trans)} {'-' if trans.transaction_type == '支出' else ''}{amount_str}",
                        f"  {category_account}"
                    ]
            
            beancount_lines.extend(lines)
            beancount_lines.append("")
        
        return "\n".join(beancount_lines)

    def _get_category_account(self, description: str) -> str:
        """
        根据交易描述获取对应的账户分类
        
        Args:
            description: 交易描述
            
        Returns:
            Beancount账户名
        """
        # 转换为小写以进行不区分大小写的匹配
        description = description.lower()
        
        # 记录最佳匹配的分类和其优先级
        best_match = None
        best_priority = -1
        
        for category, rule in self.config['rules']['categories'].items():
            if isinstance(rule, dict):
                patterns = rule.get('patterns', [])
                for pattern in patterns:
                    pattern = pattern.lower()
                    if pattern in description:
                        # 计算匹配优先级（使用模式长度作为优先级）
                        priority = len(pattern)
                        if priority > best_priority:
                            best_match = rule['account']
                            best_priority = priority
                            self.logger.debug(f"找到更好的分类匹配: {pattern} -> {rule['account']}")
        
        if best_match:
            self.logger.debug(f"商家 '{description}' 被分类为 {best_match}")
            return best_match
            
        # 如果是收入类交易，使用收入账户
        if hasattr(self, '_current_transaction') and self._current_transaction.transaction_type == '收入':
            self.logger.debug(f"使用默认收入账户: {self.config['accounts']['income']}")
            return self.config['accounts']['income']
        
        # 使用默认支出账户
        self.logger.debug(f"使用默认支出账户: {self.config['accounts']['expenses']}")
        return self.config['accounts']['expenses']
    
    def _get_account(self, transaction: CMBTransaction) -> str:
        """
        获取交易的主账户
        
        Args:
            transaction: 交易记录
            
        Returns:
            Beancount账户名
        """
        if transaction.card_number:
            # 使用卡号后四位生成账户名
            return self.config['accounts']['assets_template'].format(
                card_number=transaction.card_number
            )
        else:
            # 如果没有卡号信息，使用默认账户
            return self.config['accounts']['assets_template'].format(
                card_number='Unknown'
            )

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='将招商银行账单转换为Beancount格式')
    parser.add_argument('input', help='输入PDF文件路径')
    parser.add_argument('output', help='输出Beancount文件路径')
    parser.add_argument('--config', default='config.yaml', help='配置文件路径')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    
    args = parser.parse_args()
    
    converter = CMBBeanConverter(args.config)
    if args.debug:
        converter.logger.setLevel(logging.DEBUG)
    converter.convert_pdf(args.input, args.output)

if __name__ == '__main__':
    main() 