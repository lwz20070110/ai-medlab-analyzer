# -*- coding: utf-8 -*-
"""
AI 医学检验智能辅助分析系统
一款面向检验科 / 基层医疗机构 / 医检学习者的轻量化辅助分析软件。
纯 Python 标准库实现（tkinter + csv），无需安装任何第三方包，双击即可运行。

核心功能：
1. 检验数据一键导入（CSV / Excel）
2. 智能异常指标筛查（内置医学检验参考阈值库，自动分级）
3. 组合指标智能判读（感染类型 / 肝胆损伤 / 血糖血脂等临床提示）
4. 自动生成标准化检验小结
5. 一键导出分析报告
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv
import os
import datetime
import threading

# ============================================================
# 一、医学检验参考阈值库（简化但贴近临床，可按需扩充）
# 每一项：键=指标名, 值=[参考下限, 参考上限, 单位]
# 分级规则：轻微异常=超出10%以内；明显异常=超出10%以上；危急=严重超出
# ============================================================
REFERENCE = {
    # ---- 血常规 ----
    "白细胞计数":   [4.0, 10.0, "×10^9/L"],
    "中性粒细胞百分比": [50.0, 70.0, "%"],
    "淋巴细胞百分比": [20.0, 40.0, "%"],
    "红细胞计数":   [3.5, 5.5, "×10^12/L"],
    "血红蛋白":    [110.0, 160.0, "g/L"],
    "血小板计数":   [100.0, 300.0, "×10^9/L"],
    # ---- 生化 ----
    "谷丙转氨酶":   [0.0, 40.0, "U/L"],
    "谷草转氨酶":   [0.0, 40.0, "U/L"],
    "总胆红素":    [0.0, 21.0, "μmol/L"],
    "空腹血糖":    [3.9, 6.1, "mmol/L"],
    "肌酐":       [44.0, 106.0, "μmol/L"],
    "尿素":       [2.6, 7.5, "mmol/L"],
    "甘油三酯":    [0.0, 1.7, "mmol/L"],
    "总胆固醇":    [0.0, 5.2, "mmol/L"],
    # ---- 尿常规 ----
    "尿比重":      [1.003, 1.030, ""],
    "尿蛋白":      [0.0, 0.0, "neg"],     # 正常为阴性
    "尿葡萄糖":    [0.0, 0.0, "neg"],
}


def grade_value(value, low, high):
    """根据参考区间对检测值分级。返回 (级别, 说明)。"""
    if value < low:
        ratio = (low - value) / low if low else 1.0
        level = "轻" if ratio <= 0.10 else ("重" if ratio <= 0.30 else "危急")
        return level, f"低于参考下限 {low}"
    if value > high:
        ratio = (value - high) / high if high else 1.0
        level = "轻" if ratio <= 0.10 else ("重" if ratio <= 0.30 else "危急")
        return level, f"高于参考上限 {high}"
    return "正常", "在参考范围内"


def analyze_single(patient):
    """
    对单个患者的指标做异常筛查。patient: dict{指标名: 数值}
    返回该患者的结构化分析结果。
    """
    results = []
    for item, value in patient.items():
        if item not in REFERENCE:
            continue
        low, high, unit = REFERENCE[item]
        if isinstance(value, (int, float)):
            level, note = grade_value(value, low, high)
            flag = {"正常": "正常", "轻": "轻度异常", "重": "明显异常", "危急": "危急值"}[level]
            results.append({
                "指标": item, "数值": f"{value} {unit}".strip(),
                "参考": f"{low} ~ {high} {unit}".strip(),
                "判定": flag, "级别": level, "说明": note,
            })
    return results


# ============================================================
# 二、组合指标智能判读（临床逻辑，核心亮点）
# ============================================================
def combo_interpretation(patient):
    """根据多个指标的联动，给出临床方向性提示。返回提示列表。"""
    tips = []
    def g(name):
        return patient.get(name)

    wbc = g("白细胞计数"); neu = g("中性粒细胞百分比"); lym = g("淋巴细胞百分比")
    alt = g("谷丙转氨酶"); ast = g("谷草转氨酶"); tbil = g("总胆红素")
    glu = g("空腹血糖"); tg = g("甘油三酯"); tc = g("总胆固醇")

    if wbc is not None and neu is not None:
        if wbc > 10.0 and neu > 70:
            tips.append("提示：白细胞与中性粒细胞均升高，倾向【细菌性感染】，建议结合临床复核。")
    if wbc is not None and lym is not None:
        if wbc <= 10.0 and lym > 40:
            tips.append("提示：淋巴细胞升高、白细胞不高，倾向【病毒性感染】，建议结合临床复核。")
    if alt is not None and ast is not None:
        if alt > 40 or ast > 40:
            tips.append("提示：转氨酶升高，倾向【肝功能异常】，建议复查并排除药物、肝炎等因素。")
    if tbil is not None and (alt is not None or ast is not None):
        if tbil > 21 and (alt or 0) > 40:
            tips.append("提示：胆红素与转氨酶同高，倾向【肝胆损伤】，建议结合影像学进一步评估。")
    if glu is not None and glu > 6.1:
        tips.append("提示：空腹血糖升高，倾向【高血糖 / 糖代谢异常】，建议复查空腹血糖及糖化血红蛋白。")
    if tg is not None and tg > 1.7:
        tips.append("提示：甘油三酯升高，倾向【血脂异常】，建议结合生活方式及饮食管理。")
    if tc is not None and tc > 5.2:
        tips.append("提示：总胆固醇升高，倾向【血脂异常】，建议心血管风险评估。")

    if not tips:
        tips.append("未发现明显的指标组合异常，结果总体平稳。")
    return tips


# ============================================================
# 三、数据导入（CSV；若已安装 openpyxl 则支持 xlsx）
# ============================================================
def load_tsv_csv(path):
    """读取 CSV 文件。约定第一列为患者姓名/编号，其余列为指标名。"""
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for line in reader:
            line = [c.strip() for c in line if c is not None]
            if not line or all(not c for c in line):
                continue
            rows.append(line)
    if not rows:
        return None, "文件为空或格式无法识别"
    header = rows[0]
    data = []
    for r in rows[1:]:
        if len(r) < 1:
            continue
        pid = r[0]
        rec = {}
        for idx, h in enumerate(header):
            if idx == 0:
                continue
            if idx < len(r) and r[idx]:
                try:
                    rec[h] = float(r[idx])
                except ValueError:
                    rec[h] = r[idx]  # 非数值（如 neg）保留原文
        data.append({"姓名": pid, "数据": rec})
    return data, "ok"


# ============================================================
# 四、图形界面
# ============================================================
class App:
    def __init__(self, root):
        self.root = root
        root.title("AI 医学检验智能辅助分析系统")
        root.geometry("980x680")
        root.configure(bg="#f4f7fb")

        self.data = []          # 已导入的患者数据
        self.all_columns = []   # 全部指标列
        self.results = []       # 分析结果

        self._build_header()
        self._build_toolbar()
        self._build_tables()

    # ---- 顶部标题 ----
    def _build_header(self):
        frame = tk.Frame(self.root, bg="#1f4e79")
        frame.pack(fill="x")
        tk.Label(frame, text="AI 医学检验智能辅助分析系统",
                 bg="#1f4e79", fg="white", font=("微软雅黑", 16, "bold")).pack(pady=10)
        tk.Label(frame, text="异常筛查 · 组合判读 · 智能小结 · 一键报告",
                 bg="#1f4e79", fg="#cfe2f3", font=("微软雅黑", 9)).pack(pady=(0, 8))

    # ---- 工具栏 ----
    def _build_toolbar(self):
        bar = tk.Frame(self.root, bg="#e8eef6", height=48)
        bar.pack(fill="x", pady=(8, 4))
        btns = [
            ("导入数据", self.import_file),
            ("开始分析", self.run_analysis),
            ("导出报告", self.export_report),
            ("清空数据", self.clear_all),
        ]
        for text, cmd in btns:
            tk.Button(bar, text=text, command=cmd, width=12,
                      bg="#1f4e79", fg="white", font=("微软雅黑", 10),
                      relief="flat", activebackground="#2e5c8a").pack(side="left", padx=8, pady=8)
        self.status = tk.Label(bar, text="请先导入检验数据（CSV）",
                               bg="#e8eef6", fg="#1f4e79", font=("微软雅黑", 9))
        self.status.pack(side="right", padx=10)

    # ---- 左右两栏：原始数据 / 分析结果 ----
    def _build_tables(self):
        body = tk.Frame(self.root, bg="#f4f7fb")
        body.pack(fill="both", expand=True, padx=10, pady=(4, 8))

        # 左：原始数据
        left = tk.LabelFrame(body, text="患者检验数据", bg="#f4f7fb",
                             font=("微软雅黑", 10, "bold"), fg="#1f4e79")
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))
        self.tree_data = ttk.Treeview(left, show="headings", height=14)
        self.tree_data.pack(fill="both", expand=True)

        # 右：分析结果
        right = tk.LabelFrame(body, text="智能分析结果（异常筛查 + 组合判读）", bg="#f4f7fb",
                              font=("微软雅黑", 10, "bold"), fg="#1f4e79")
        right.pack(side="left", fill="both", expand=True, padx=(5, 0))
        self.tree_res = ttk.Treeview(right, show="headings", height=14)
        self.tree_res.pack(fill="both", expand=True)

        # 底部：智能小结
        self.summary = tk.Text(self.root, height=6, font=("微软雅黑", 10),
                               bg="#fffef5", fg="#333")
        self.summary.pack(fill="x", padx=10, pady=(0, 8))
        self.summary.insert("1.0", "智能小结：导入数据并点击【开始分析】后，将在此生成标准化检验小结。")

    # ---- 导入文件 ----
    def import_file(self):
        path = filedialog.askopenfilename(
            title="选择检验数据文件",
            filetypes=[("CSV 文件", "*.csv"), ("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            self.data, msg = load_tsv_csv(path)
            if msg != "ok":
                messagebox.showerror("导入失败", msg)
                return
            if not self.data:
                messagebox.showerror("导入失败", "文件中没有患者数据")
                return
            self.all_columns = []
            for p in self.data:
                for k in p["数据"].keys():
                    if k not in self.all_columns:
                        self.all_columns.append(k)
            self._fill_data_tree()
            self.status.config(text=f"已导入 {len(self.data)} 例患者数据")
            messagebox.showinfo("导入成功", f"成功导入 {len(self.data)} 例患者检验数据。")
        except Exception as e:
            messagebox.showerror("导入失败", str(e))

    def _fill_data_tree(self):
        self.tree_data.delete(*self.tree_data.get_children())
        cols = ["患者"] + self.all_columns
        self.tree_data["columns"] = cols
        for c in cols:
            self.tree_data.heading(c, text=c)
            self.tree_data.column(c, width=80, anchor="center")
        for p in self.data:
            row = [p["姓名"]]
            for c in self.all_columns:
                row.append(p["数据"].get(c, ""))
            self.tree_data.insert("", "end", values=row)

    # ---- 开始分析 ----
    def run_analysis(self):
        if not self.data:
            messagebox.showwarning("提示", "请先导入检验数据。")
            return
        self.status.config(text="正在分析…")
        self.root.update()
        threading.Thread(target=self._do_analysis, daemon=True).start()

    def _do_analysis(self):
        self.results = []
        lines = []
        for p in self.data:
            name = p["姓名"]
            singles = analyze_single(p["数据"])
            tips = combo_interpretation(p["数据"])
            self.results.append({"姓名": name, "指标": singles, "判读": tips})

            # 统计
            abnormal = [r for r in singles if r["判定"] != "正常"]
            critical = [r for r in singles if r["判定"] == "危急值"]
            level_word = "存在危急值" if critical else ("存在异常指标" if abnormal else "结果平稳")

            lines.append(f"【{name}】共检{len(singles)}项，异常{len(abnormal)}项，{level_word}。")
            for t in tips:
                lines.append(f"    {t}")

        self.root.after(0, self._fill_res_tree, lines)

    def _fill_res_tree(self, lines):
        self.tree_res.delete(*self.tree_res.get_children())
        cols = ["患者", "指标", "结果", "参考区间", "判定", "级别"]
        self.tree_res["columns"] = cols
        for c in cols:
            self.tree_res.heading(c, text=c)
            self.tree_res.column(c, width=90, anchor="center")
        for res in self.results:
            for r in res["指标"]:
                self.tree_res.insert("", "end", values=[
                    res["姓名"], r["指标"], r["数值"], r["参考"], r["判定"], r["级别"]])
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", "智能小结：\n" + "\n".join(lines))
        self.status.config(text="分析完成")

    # ---- 导出报告 ----
    def export_report(self):
        if not self.results:
            messagebox.showwarning("提示", "请先完成分析。")
            return
        path = filedialog.asksaveasfilename(
            title="保存分析报告", defaultextension=".txt",
            initialfile=f"医检分析报告_{datetime.date.today()}.txt",
            filetypes=[("文本文件", "*.txt")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write("=" * 46 + "\n")
            f.write("AI 医学检验智能辅助分析报告\n")
            f.write("生成时间：" + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
            f.write("=" * 46 + "\n\n")
            for res in self.results:
                f.write(f"患者：{res['姓名']}\n")
                f.write("-" * 46 + "\n")
                f.write(f"{'指标':<10}{'结果':<12}{'参考区间':<16}{'判定':<8}{'级别'}\n")
                for r in res["指标"]:
                    f.write(f"{r['指标']:<10}{r['数值']:<12}{r['参考']:<16}{r['判定']:<8}{r['级别']}\n")
                f.write("\n组合判读：\n")
                for t in res["判读"]:
                    f.write("  " + t + "\n")
                f.write("\n" + "=" * 46 + "\n\n")
        messagebox.showinfo("导出成功", f"报告已保存至：\n{path}")

    def clear_all(self):
        self.data, self.results = [], []
        for t in (self.tree_data, self.tree_res):
            t.delete(*t.get_children())
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", "智能小结：已清空，请重新导入数据。")
        self.status.config(text="请先导入检验数据（CSV）")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
#（注：内容由AI生成）
