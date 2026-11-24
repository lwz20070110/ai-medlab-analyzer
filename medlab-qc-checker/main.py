# -*- coding: utf-8 -*-
"""
医学检验报告质控纠错系统
面向检验科报告审核 / 实习生带教的轻量化质控辅助软件。
纯 Python 标准库实现（tkinter + csv），无需安装任何第三方包，双击即可运行。

核心功能：
1. 批量导入检验报告（CSV）
2. 生理极值合理性校验（识别小数点错位、量级错误等疑似录入错误）
3. 参考区间偏离分级（轻度 / 明显 / 疑似录入错误）
4. 指标逻辑矛盾校验（构成比之和、红细胞与血红蛋白方向一致性等）
5. 缺项检查与危急值标记，自动生成质控整改小结并导出报告

说明：本系统仅为质控辅助提示，所有问题均需检验人员结合原始标本与仪器复核。
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv
import datetime

# ============================================================
# 一、指标质控参数库
# 结构：指标 -> [参考下限, 参考上限, 生理绝对下限, 生理绝对上限, 单位]
# 参考区间用于偏离分级；生理极值用于识别量级 / 小数点录入错误。
# ============================================================
QC_RULES = {
    "白细胞计数":   [4.0, 10.0, 1.0, 50.0, "×10^9/L"],
    "中性粒细胞百分比": [50.0, 70.0, 1.0, 99.0, "%"],
    "淋巴细胞百分比": [20.0, 40.0, 1.0, 99.0, "%"],
    "红细胞计数":   [3.5, 5.5, 2.0, 8.0, "×10^12/L"],
    "血红蛋白":    [110.0, 160.0, 50.0, 220.0, "g/L"],
    "血小板计数":   [100.0, 300.0, 20.0, 1000.0, "×10^9/L"],
    "谷丙转氨酶":   [0.0, 40.0, 0.0, 1000.0, "U/L"],
    "谷草转氨酶":   [0.0, 40.0, 0.0, 1000.0, "U/L"],
    "总胆红素":    [0.0, 21.0, 0.0, 300.0, "μmol/L"],
    "空腹血糖":    [3.9, 6.1, 2.0, 35.0, "mmol/L"],
    "肌酐":       [44.0, 106.0, 20.0, 900.0, "μmol/L"],
    "尿素":       [2.6, 7.5, 0.5, 50.0, "mmol/L"],
    "甘油三酯":    [0.0, 1.7, 0.0, 20.0, "mmol/L"],
    "总胆固醇":    [0.0, 5.2, 0.0, 20.0, "mmol/L"],
}

# 关键指标（缺项时需要提示）
KEY_ITEMS = ["白细胞计数", "血红蛋白", "谷丙转氨酶", "空腹血糖"]


def load_csv(path):
    """读取 CSV，返回 (records, msg)。第一列为患者，其余列为指标。"""
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for line in csv.reader(f):
            line = [c.strip() for c in line if c is not None]
            if line and any(line):
                rows.append(line)
    if not rows:
        return None, "文件为空或格式无法识别"
    header = rows[0]
    data = []
    for r in rows[1:]:
        if len(r) < 1 or not r[0]:
            continue
        rec = {}
        for idx, h in enumerate(header):
            if idx == 0:
                continue
            if idx < len(r) and r[idx]:
                try:
                    rec[h] = float(r[idx])
                except ValueError:
                    rec[h] = r[idx]
        data.append({"姓名": r[0], "数据": rec})
    return data, "ok"


def check_value(item, value):
    """
    单指标数值质控。返回问题字典或 None。
    严重度：高危=疑似录入错误/危急；中危=明显偏离需复核；提示=轻度偏离。
    """
    if item not in QC_RULES:
        return None
    low, high, abs_low, abs_high, unit = QC_RULES[item]
    if not isinstance(value, (int, float)):
        return None

    # 1. 生理极值越界：量级或小数点错误嫌疑
    if value < abs_low or value > abs_high:
        return {"项目": item, "当前值": f"{value} {unit}",
                "类型": "疑似录入错误（超出生理极值）", "严重度": "高危",
                "建议": f"核对原始标本与录入数值，确认是否存在小数点错位或单位混淆（生理范围 {abs_low}~{abs_high} {unit}）。"}

    # 2. 参考区间偏离分级
    if value < low:
        ratio = (low - value) / low if low else 1.0
        if value < low * 0.6:
            return {"项目": item, "当前值": f"{value} {unit}",
                    "类型": "数值显著偏低", "严重度": "高危",
                    "建议": f"结果远低于参考下限 {low} {unit}，建议复核标本与仪器结果。"}
        level = "中危" if ratio > 0.10 else "提示"
        return {"项目": item, "当前值": f"{value} {unit}",
                "类型": "低于参考区间", "严重度": level,
                "建议": f"低于参考下限 {low} {unit}，建议结合临床与复查结果复核。"}
    if value > high:
        ratio = (value - high) / high if high else 1.0
        if ratio > 1.0:
            return {"项目": item, "当前值": f"{value} {unit}",
                    "类型": "疑似录入错误（超出上限一倍以上）", "严重度": "高危",
                    "建议": f"数值超过上限 {high} {unit} 一倍以上，排查小数点 / 单位 / 录入笔误。"}
        level = "中危" if ratio > 0.10 else "提示"
        return {"项目": item, "当前值": f"{value} {unit}",
                "类型": "高于参考区间", "严重度": level,
                "建议": f"高于参考上限 {high} {unit}，建议结合临床与复查结果复核。"}
    return None


def check_consistency(rec):
    """指标间逻辑矛盾校验。返回问题列表。"""
    issues = []

    def g(name):
        return rec.get(name)

    neu = g("中性粒细胞百分比"); lym = g("淋巴细胞百分比")
    if isinstance(neu, (int, float)) and isinstance(lym, (int, float)):
        s = neu + lym
        if s < 90 or s > 110:
            issues.append({
                "项目": "中性粒%+淋巴%构成比", "当前值": f"{neu:.0f}% + {lym:.0f}% = {s:.0f}%",
                "类型": "构成比逻辑矛盾", "严重度": "中危",
                "建议": "两类白细胞百分比之和明显偏离 100%，核对分类计数是否录入完整。"})

    rbc = g("红细胞计数"); hgb = g("血红蛋白")
    if isinstance(rbc, (int, float)) and isinstance(hgb, (int, float)):
        rbc_low, rbc_high = 3.5, 5.5
        hgb_low, hgb_high = 110.0, 160.0
        rbc_low_f, rbc_high_f = rbc < rbc_low, rbc > rbc_high
        hgb_low_f, hgb_high_f = hgb < hgb_low, hgb > hgb_high
        if (rbc_low_f and hgb_high_f) or (rbc_high_f and hgb_low_f):
            issues.append({
                "项目": "红细胞计数 / 血红蛋白", "当前值": f"RBC {rbc}，HGB {hgb}",
                "类型": "指标方向不一致", "严重度": "中危",
                "建议": "红细胞计数与血红蛋白变化方向不一致，建议复核两项检测结果是否匹配。"})

    return issues


def check_missing(rec):
    """关键指标缺项检查。返回问题列表。"""
    issues = []
    for item in KEY_ITEMS:
        if item not in rec or rec[item] in (None, "", "neg"):
            issues.append({
                "项目": item, "当前值": "—", "类型": "关键指标缺项",
                "严重度": "提示", "建议": f"缺少【{item}】结果，确认是否漏检或漏录。"})
    return issues


def run_qc(records):
    """对全部患者执行质控，返回问题清单与统计小结。"""
    issues = []
    for p in records:
        name, rec = p["姓名"], p["数据"]
        for item, val in rec.items():
            q = check_value(item, val)
            if q:
                q["患者"] = name
                issues.append(q)
        for q in check_consistency(rec):
            q["患者"] = name
            issues.append(q)
        for q in check_missing(rec):
            q["患者"] = name
            issues.append(q)

    high = [i for i in issues if i["严重度"] == "高危"]
    mid = [i for i in issues if i["严重度"] == "中危"]
    tip = [i for i in issues if i["严重度"] == "提示"]
    summary = {
        "患者数": len(records),
        "问题总数": len(issues),
        "高危": len(high), "中危": len(mid), "提示": len(tip),
    }
    return issues, summary


# ============================================================
# 二、图形界面
# ============================================================
class App:
    def __init__(self, root):
        self.root = root
        root.title("医学检验报告质控纠错系统")
        root.geometry("1000x700")
        root.configure(bg="#f4f7fb")
        self.records = []
        self.issues = []
        self.summary = {}
        self._build_header()
        self._build_toolbar()
        self._build_body()

    def _build_header(self):
        frame = tk.Frame(self.root, bg="#1f4e79")
        frame.pack(fill="x")
        tk.Label(frame, text="医学检验报告质控纠错系统",
                 bg="#1f4e79", fg="white", font=("微软雅黑", 16, "bold")).pack(pady=10)
        tk.Label(frame, text="极值校验 · 逻辑矛盾核查 · 缺项提示 · 质控整改报告",
                 bg="#1f4e79", fg="#cfe2f3", font=("微软雅黑", 9)).pack(pady=(0, 8))

    def _build_toolbar(self):
        bar = tk.Frame(self.root, bg="#e8eef6", height=48)
        bar.pack(fill="x", pady=(8, 4))
        for text, cmd in [("导入报告", self.import_file),
                          ("开始质控", self.run_qc),
                          ("导出报告", self.export_report),
                          ("清空", self.clear_all)]:
            tk.Button(bar, text=text, command=cmd, width=12, bg="#1f4e79",
                      fg="white", font=("微软雅黑", 10), relief="flat",
                      activebackground="#2e5c8a").pack(side="left", padx=8, pady=8)
        self.status = tk.Label(bar, text="请先导入检验报告（CSV）",
                               bg="#e8eef6", fg="#1f4e79", font=("微软雅黑", 9))
        self.status.pack(side="right", padx=10)

    def _build_body(self):
        body = tk.Frame(self.root, bg="#f4f7fb")
        body.pack(fill="both", expand=True, padx=10, pady=(4, 8))
        left = tk.LabelFrame(body, text="导入的检验报告", bg="#f4f7fb",
                             font=("微软雅黑", 10, "bold"), fg="#1f4e79")
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))
        self.tree_data = ttk.Treeview(left, show="headings", height=14)
        self.tree_data.pack(fill="both", expand=True)
        right = tk.LabelFrame(body, text="质控问题清单", bg="#f4f7fb",
                              font=("微软雅黑", 10, "bold"), fg="#1f4e79")
        right.pack(side="left", fill="both", expand=True, padx=(5, 0))
        self.tree_res = ttk.Treeview(right, show="headings", height=14)
        self.tree_res.pack(fill="both", expand=True)
        self.summary_box = tk.Text(self.root, height=6, font=("微软雅黑", 10),
                                   bg="#fffef5", fg="#333")
        self.summary_box.pack(fill="x", padx=10, pady=(0, 8))
        self.summary_box.insert("1.0", "质控小结：导入报告并点击【开始质控】后，将在此汇总问题分级与整改建议。")

    def import_file(self):
        path = filedialog.askopenfilename(
            title="选择检验报告",
            filetypes=[("CSV 文件", "*.csv"), ("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            self.records, msg = load_csv(path)
            if msg != "ok":
                messagebox.showerror("导入失败", msg)
                return
            if not self.records:
                messagebox.showerror("导入失败", "文件中没有患者数据")
                return
            self._fill_data_tree()
            self.status.config(text=f"已导入 {len(self.records)} 例报告")
            messagebox.showinfo("导入成功", f"成功导入 {len(self.records)} 例检验报告。")
        except Exception as e:
            messagebox.showerror("导入失败", str(e))

    def _fill_data_tree(self):
        cols = ["患者"]
        for p in self.records:
            for k in p["数据"].keys():
                if k not in cols:
                    cols.append(k)
        self.tree_data["columns"] = cols
        for c in cols:
            self.tree_data.heading(c, text=c)
            self.tree_data.column(c, width=80, anchor="center")
        for p in self.records:
            row = [p["姓名"]] + [p["数据"].get(c, "") for c in cols[1:]]
            self.tree_data.insert("", "end", values=row)

    def run_qc(self):
        if not self.records:
            messagebox.showwarning("提示", "请先导入检验报告。")
            return
        self.status.config(text="正在质控核查…")
        self.root.update()
        self.issues, self.summary = run_qc(self.records)
        self._fill_res_tree()
        self.status.config(text="质控完成")

    def _fill_res_tree(self):
        self.tree_res.delete(*self.tree_res.get_children())
        cols = ["患者", "项目", "当前值", "问题类型", "严重度", "复核建议"]
        self.tree_res["columns"] = cols
        widths = [70, 120, 110, 150, 70, 260]
        for c, w in zip(cols, widths):
            self.tree_res.heading(c, text=c)
            self.tree_res.column(c, width=w, anchor="center" if c != "复核建议" else "w")
        tag_color = {"高危": "#f8d7da", "中危": "#fff3cd", "提示": "#d1ecf1"}
        for sev, color in tag_color.items():
            self.tree_res.tag_configure(sev, background=color)
        for i in self.issues:
            self.tree_res.insert("", "end", values=[
                i["患者"], i["项目"], i["当前值"], i["类型"], i["严重度"], i["建议"]],
                tags=(i["严重度"],))
        s = self.summary
        text = (f"质控小结：共核查 {s['患者数']} 例报告，发现问题 {s['问题总数']} 条"
                f"（高危 {s['高危']}、中危 {s['中危']}、提示 {s['提示']}）。\n"
                "高危项须优先复核原始标本与录入；中危项建议结合临床与复查结果确认；提示项为缺项或轻度偏离，按需补录。\n"
                "注：本系统仅为质控辅助，最终结果以检验人员复核为准。")
        self.summary_box.delete("1.0", "end")
        self.summary_box.insert("1.0", text)

    def export_report(self):
        if not self.issues:
            messagebox.showwarning("提示", "请先完成质控。")
            return
        path = filedialog.asksaveasfilename(
            title="保存质控报告", defaultextension=".txt",
            initialfile=f"医检质控报告_{datetime.date.today()}.txt",
            filetypes=[("文本文件", "*.txt")])
        if not path:
            return
        s = self.summary
        with open(path, "w", encoding="utf-8") as f:
            f.write("=" * 50 + "\n")
            f.write("医学检验报告质控纠错报告\n")
            f.write("生成时间：" + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
            f.write("=" * 50 + "\n")
            f.write(f"核查例数：{s['患者数']}    问题总数：{s['问题总数']}\n")
            f.write(f"高危：{s['高危']}    中危：{s['中危']}    提示：{s['提示']}\n\n")
            for i in self.issues:
                f.write(f"[{i['严重度']}] {i['患者']} | {i['项目']} | {i['当前值']}\n")
                f.write(f"    问题：{i['类型']}\n    建议：{i['建议']}\n\n")
        messagebox.showinfo("导出成功", f"质控报告已保存至：\n{path}")

    def clear_all(self):
        self.records, self.issues, self.summary = [], [], {}
        self.tree_data.delete(*self.tree_data.get_children())
        self.tree_res.delete(*self.tree_res.get_children())
        self.summary_box.delete("1.0", "end")
        self.summary_box.insert("1.0", "质控小结：已清空，请重新导入报告。")
        self.status.config(text="请先导入检验报告（CSV）")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
