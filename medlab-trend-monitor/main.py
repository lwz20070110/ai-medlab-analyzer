# -*- coding: utf-8 -*-
"""
医学检验指标趋势动态监测系统
面向随访患者 / 慢病管理 / 检验教学的轻量化趋势分析软件。
纯 Python 标准库实现（tkinter + csv + Canvas），无需安装任何第三方包，双击即可运行。

核心功能：
1. 导入同一患者多次（按日期）检验数据（CSV）
2. 选择患者与指标，自动绘制折线趋势图（参考区间上下限虚线标注）
3. 线性回归 + 相邻方向判断，识别持续升高 / 持续下降 / 波动 / 平稳
4. 自动标注超范围异常点，生成趋势变化小结
5. 一键导出趋势分析报告

说明：本系统仅为趋势辅助提示，不替代临床诊断，结果需结合病史与复查复核。
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv
import datetime

# ============================================================
# 一、指标参考区间库 [下限, 上限, 单位]
# ============================================================
REF = {
    "白细胞计数":   [4.0, 10.0, "×10^9/L"],
    "血红蛋白":    [110.0, 160.0, "g/L"],
    "谷丙转氨酶":   [0.0, 40.0, "U/L"],
    "空腹血糖":    [3.9, 6.1, "mmol/L"],
    "血小板计数":   [100.0, 300.0, "×10^9/L"],
    "甘油三酯":    [0.0, 1.7, "mmol/L"],
}


def load_csv(path):
    """读取 CSV。约定列：日期,患者,其余为指标。返回 (records, msg)。"""
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for line in csv.reader(f):
            line = [c.strip() for c in line if c is not None]
            if line and any(line):
                rows.append(line)
    if not rows:
        return None, "文件为空或格式无法识别"
    header = rows[0]
    idx_date, idx_pid = 0, 1
    data = []
    for r in rows[1:]:
        if len(r) < 2 or not r[idx_pid]:
            continue
        rec = {"日期": r[idx_date], "患者": r[idx_pid], "指标": {}}
        for i, h in enumerate(header):
            if i in (idx_date, idx_pid):
                continue
            if i < len(r) and r[i]:
                try:
                    rec["指标"][h] = float(r[i])
                except ValueError:
                    rec["指标"][h] = r[i]
        data.append(rec)
    return data, "ok"


def group_by_patient(records):
    """按患者分组并按日期排序。返回 {患者: [{日期, 指标}]}。"""
    grouped = {}
    for rec in records:
        grouped.setdefault(rec["患者"], []).append(
            {"日期": rec["日期"], "指标": rec["指标"]})
    for name in grouped:
        grouped[name].sort(key=lambda x: x["日期"])
    return grouped


def linear_slope(values):
    """最小二乘斜率（x 为序列序号 0..n-1）。"""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    sx, sy = sum(xs), sum(values)
    sxy = sum(x * y for x, y in zip(xs, values))
    sxx = sum(x * x for x in xs)
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0.0
    return (n * sxy - sx * sy) / denom


def analyze_trend(values, dates, item):
    """
    趋势分析。返回结论字典：
    结论 / 起点 / 终点 / 变化幅度 / 斜率 / 异常点 / 说明列表。
    """
    low, high, unit = REF.get(item, [None, None, ""])
    n = len(values)
    res = {"结论": "数据不足", "起点": values[0], "终点": values[-1],
           "幅度": 0.0, "斜率": 0.0, "异常点": [], "说明": []}

    # 异常点（超参考区间）
    if low is not None:
        for d, v in zip(dates, values):
            if v < low or v > high:
                res["异常点"].append({"日期": d, "数值": v})

    if n < 3:
        res["结论"] = "样本不足"
        res["说明"].append("次数少于 3 次，暂不做趋势判断，建议继续随访复查。")
        return res

    slope = linear_slope(values)
    mean_v = sum(values) / n or 1.0
    rel_slope = slope / mean_v  # 归一化斜率，便于跨指标比较

    # 相邻方向
    ups = downs = 0
    for a, b in zip(values, values[1:]):
        if b > a:
            ups += 1
        elif b < a:
            downs += 1
    segments = n - 1
    up_ratio = ups / segments
    down_ratio = downs / segments

    first, last = values[0], values[-1]
    change = (last - first) / first if first else 0.0
    res["斜率"], res["幅度"] = slope, change

    # 方向一致优先：单调同向即判持续升高 / 下降
    if slope > 0 and up_ratio >= 2 / 3:
        res["结论"] = "持续升高"
    elif slope < 0 and down_ratio >= 2 / 3:
        res["结论"] = "持续下降"
    # 小幅波动且变化极微，视为平稳
    elif abs(change) < 0.03 and abs(rel_slope) < 0.01:
        res["结论"] = "总体平稳"
    elif abs(rel_slope) < 0.03 and abs(change) < 0.10 and (ups == 0 or downs == 0):
        res["结论"] = "总体平稳"
    else:
        res["结论"] = "波动变化"

    # 说明文案
    if res["结论"] == "持续升高":
        res["说明"].append(f"指标呈上升趋势，由 {first} 升至 {last}，累计变化 {change * 100:.1f}%，建议密切随访、排查原因。")
    elif res["结论"] == "持续下降":
        res["说明"].append(f"指标呈下降趋势，由 {first} 降至 {last}，累计变化 {change * 100:.1f}%，结合临床评估变化原因。")
    elif res["结论"] == "波动变化":
        res["说明"].append(f"指标上下波动（上升 {ups} 段、下降 {downs} 段），未见明确单向趋势，建议增加随访次数观察。")
    else:
        res["说明"].append("指标在随访期内基本平稳，无明显单向变化。")
    if res["异常点"]:
        res["说明"].append(f"其中 {len(res['异常点'])} 次结果超出参考区间（{low}~{high} {unit}），建议重点复核。")
    res["说明"].append("注：以上为趋势辅助提示，需结合病史、临床表现与复查结果综合判断。")
    return res


# ============================================================
# 二、图形界面
# ============================================================
class App:
    def __init__(self, root):
        self.root = root
        root.title("医学检验指标趋势动态监测系统")
        root.geometry("1000x720")
        root.configure(bg="#f4f7fb")
        self.grouped = {}
        self.patients = []
        self.items = []
        self.current = None  # 当前分析结果 {日期, 数值, 指标, 结论}

        self._build_header()
        self._build_toolbar()
        self._build_selector()
        self._build_canvas()
        self._build_summary()

    def _build_header(self):
        frame = tk.Frame(self.root, bg="#1f4e79")
        frame.pack(fill="x")
        tk.Label(frame, text="医学检验指标趋势动态监测系统",
                 bg="#1f4e79", fg="white", font=("微软雅黑", 16, "bold")).pack(pady=10)
        tk.Label(frame, text="多次结果曲线 · 升降波动识别 · 异常点标注 · 趋势小结",
                 bg="#1f4e79", fg="#cfe2f3", font=("微软雅黑", 9)).pack(pady=(0, 8))

    def _build_toolbar(self):
        bar = tk.Frame(self.root, bg="#e8eef6", height=46)
        bar.pack(fill="x", pady=(8, 4))
        for text, cmd in [("导入数据", self.import_file),
                          ("导出报告", self.export_report),
                          ("清空", self.clear_all)]:
            tk.Button(bar, text=text, command=cmd, width=12, bg="#1f4e79",
                      fg="white", font=("微软雅黑", 10), relief="flat",
                      activebackground="#2e5c8a").pack(side="left", padx=8, pady=8)
        self.status = tk.Label(bar, text="请先导入多次检验数据（CSV）",
                               bg="#e8eef6", fg="#1f4e79", font=("微软雅黑", 9))
        self.status.pack(side="right", padx=10)

    def _build_selector(self):
        bar = tk.Frame(self.root, bg="#f4f7fb")
        bar.pack(fill="x", padx=10)
        tk.Label(bar, text="患者：", bg="#f4f7fb", font=("微软雅黑", 10)).pack(side="left")
        self.cb_patient = ttk.Combobox(bar, width=12, state="readonly")
        self.cb_patient.pack(side="left", padx=(4, 16))
        tk.Label(bar, text="指标：", bg="#f4f7fb", font=("微软雅黑", 10)).pack(side="left")
        self.cb_item = ttk.Combobox(bar, width=14, state="readonly")
        self.cb_item.pack(side="left", padx=(4, 16))
        tk.Button(bar, text="绘制趋势", command=self.draw_trend, bg="#2e7d32",
                  fg="white", font=("微软雅黑", 10), relief="flat",
                  activebackground="#388e3c").pack(side="left")

    def _build_canvas(self):
        frame = tk.LabelFrame(self.root, text="指标趋势曲线", bg="#f4f7fb",
                              font=("微软雅黑", 10, "bold"), fg="#1f4e79")
        frame.pack(fill="both", expand=True, padx=10, pady=6)
        self.canvas = tk.Canvas(frame, bg="white", height=300)
        self.canvas.pack(fill="both", expand=True, padx=6, pady=6)

    def _build_summary(self):
        self.summary_box = tk.Text(self.root, height=7, font=("微软雅黑", 10),
                                   bg="#fffef5", fg="#333")
        self.summary_box.pack(fill="x", padx=10, pady=(0, 8))
        self.summary_box.insert("1.0", "趋势小结：选择患者与指标后点击【绘制趋势】，将在此生成趋势判断与变化说明。")

    def import_file(self):
        path = filedialog.askopenfilename(
            title="选择多次检验数据",
            filetypes=[("CSV 文件", "*.csv"), ("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            records, msg = load_csv(path)
            if msg != "ok":
                messagebox.showerror("导入失败", msg)
                return
            if not records:
                messagebox.showerror("导入失败", "文件中没有数据")
                return
            self.grouped = group_by_patient(records)
            self.patients = sorted(self.grouped.keys())
            self.items = []
            for rec in records:
                for k in rec["指标"].keys():
                    if k not in self.items:
                        self.items.append(k)
            self.cb_patient["values"] = self.patients
            self.cb_item["values"] = self.items
            if self.patients:
                self.cb_patient.current(0)
            if self.items:
                self.cb_item.current(0)
            self.status.config(text=f"已导入 {len(records)} 条随访记录，{len(self.patients)} 位患者")
            messagebox.showinfo("导入成功", f"成功导入 {len(records)} 条随访记录。")
        except Exception as e:
            messagebox.showerror("导入失败", str(e))

    def draw_trend(self):
        if not self.grouped:
            messagebox.showwarning("提示", "请先导入检验数据。")
            return
        patient = self.cb_patient.get()
        item = self.cb_item.get()
        if not patient or not item:
            messagebox.showwarning("提示", "请选择患者和指标。")
            return
        series = self.grouped[patient]
        dates, values = [], []
        for s in series:
            v = s["指标"].get(item)
            if isinstance(v, (int, float)):
                dates.append(s["日期"])
                values.append(v)
        if len(values) < 2:
            messagebox.showwarning("提示", "该患者此指标有效数据不足 2 次，无法绘图。")
            return
        conclusion = analyze_trend(values, dates, item)
        self.current = {"患者": patient, "指标": item, "dates": dates,
                        "values": values, "结论": conclusion}
        self._render_canvas()
        self._fill_summary()

    def _render_canvas(self):
        cv = self.canvas
        cv.delete("all")
        d = self.current
        dates, values, item = d["dates"], d["values"], d["指标"]
        low, high, unit = REF.get(item, [None, None, ""])

        W, H = cv.winfo_width(), cv.winfo_height()
        if W < 100:
            W, H = 880, 300
        pad_l, pad_r, pad_t, pad_b = 60, 24, 24, 44

        ymin = min(values + ([low] if low is not None else []))
        ymax = max(values + ([high] if high is not None else []))
        span = ymax - ymin or 1.0
        ymin -= span * 0.12
        ymax += span * 0.12

        def to_x(i):
            if len(values) == 1:
                return pad_l + (W - pad_l - pad_r) / 2
            return pad_l + i * (W - pad_l - pad_r) / (len(values) - 1)

        def to_y(v):
            return pad_t + (ymax - v) * (H - pad_t - pad_b) / (ymax - ymin)

        # 参考区间底色与虚线
        if low is not None:
            cv.create_rectangle(pad_l, to_y(high), W - pad_r, to_y(low),
                                fill="#eef6ee", outline="")
            cv.create_line(pad_l, to_y(high), W - pad_r, to_y(high),
                           fill="#888", dash=(4, 3), width=1)
            cv.create_line(pad_l, to_y(low), W - pad_r, to_y(low),
                           fill="#888", dash=(4, 3), width=1)
            cv.create_text(pad_l - 6, to_y(high), text=f"上限 {high}",
                           anchor="e", fill="#666", font=("微软雅黑", 8))
            cv.create_text(pad_l - 6, to_y(low), text=f"下限 {low}",
                           anchor="e", fill="#666", font=("微软雅黑", 8))

        # 坐标轴
        cv.create_line(pad_l, H - pad_b, W - pad_r, H - pad_b, fill="#333")
        cv.create_line(pad_l, pad_t, pad_l, H - pad_b, fill="#333")

        # 折线
        pts = [(to_x(i), to_y(v)) for i, v in enumerate(values)]
        if len(pts) > 1:
            cv.create_line(pts, fill="#1f4e79", width=2)
        for i, (x, y) in enumerate(pts):
            abnormal = low is not None and (values[i] < low or values[i] > high)
            color = "#c62828" if abnormal else "#1f4e79"
            cv.create_oval(x - 5, y - 5, x + 5, y + 5, fill=color, outline="white")
            cv.create_text(x, y - 14, text=f"{values[i]:g}", fill=color,
                           font=("微软雅黑", 8), anchor="center")
            label = dates[i][5:] if len(dates[i]) >= 10 else dates[i]
            cv.create_text(x, H - pad_b + 16, text=label, fill="#333",
                           font=("微软雅黑", 8), anchor="center")

        # 标题
        cv.create_text(pad_l, 8, text=f"{d['患者']} · {item}（{unit}）  趋势：{d['结论']['结论']}",
                       anchor="w", fill="#1f4e79", font=("微软雅黑", 10, "bold"))

    def _fill_summary(self):
        d = self.current
        c = d["结论"]
        lines = [f"【{d['患者']} · {d['指标']}】共 {len(d['values'])} 次随访，趋势判断：{c['结论']}。"]
        lines.append(f"起点 {c['起点']:g} → 终点 {c['终点']:g}，累计变化 {c['幅度'] * 100:.1f}%。")
        for s in c["说明"]:
            lines.append("· " + s)
        self.summary_box.delete("1.0", "end")
        self.summary_box.insert("1.0", "趋势小结：\n" + "\n".join(lines))

    def export_report(self):
        if not self.current:
            messagebox.showwarning("提示", "请先绘制趋势。")
            return
        path = filedialog.asksaveasfilename(
            title="保存趋势报告", defaultextension=".txt",
            initialfile=f"医检趋势报告_{datetime.date.today()}.txt",
            filetypes=[("文本文件", "*.txt")])
        if not path:
            return
        d = self.current
        c = d["结论"]
        with open(path, "w", encoding="utf-8") as f:
            f.write("=" * 50 + "\n")
            f.write("医学检验指标趋势分析报告\n")
            f.write("生成时间：" + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
            f.write("=" * 50 + "\n")
            f.write(f"患者：{d['患者']}    指标：{d['指标']}\n")
            f.write(f"趋势结论：{c['结论']}    起点 {c['起点']:g} → 终点 {c['终点']:g}"
                    f"（变化 {c['幅度'] * 100:.1f}%）\n\n")
            f.write("历次结果：\n")
            for dt, v in zip(d["dates"], d["values"]):
                f.write(f"  {dt}  {v:g}\n")
            f.write("\n趋势说明：\n")
            for s in c["说明"]:
                f.write("  " + s + "\n")
        messagebox.showinfo("导出成功", f"趋势报告已保存至：\n{path}")

    def clear_all(self):
        self.grouped, self.patients, self.items, self.current = {}, [], [], None
        self.cb_patient["values"], self.cb_item["values"] = [], []
        self.canvas.delete("all")
        self.summary_box.delete("1.0", "end")
        self.summary_box.insert("1.0", "趋势小结：已清空，请重新导入数据。")
        self.status.config(text="请先导入多次检验数据（CSV）")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
