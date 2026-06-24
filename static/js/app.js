const { createApp } = Vue;

const ORDER_TYPES = [
  { label: "中餐", value: "中餐" },
  { label: "晚餐", value: "晚餐" }
];

const FORM_TYPES = [
  { label: "堂食", value: "堂食" },
  { label: "盒饭", value: "盒饭" }
];

const DISPLAY_TEXT = new Map([
  ...ORDER_TYPES.map((item) => [item.value, item.label]),
  ...FORM_TYPES.map((item) => [item.value, item.label])
]);

function formatDateText(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function todayText() {
  return formatDateText(new Date());
}

function parseDateText(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return null;

  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(year, month - 1, day);

  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    return null;
  }

  return date;
}

function getApiBase() {
  const defaultApiBase = window.location.protocol === "file:"
    ? "http://127.0.0.1:8000"
    : window.location.origin;
  const savedApiBase = localStorage.getItem("happyLunchApiBase") || "";

  if (savedApiBase.includes("127.0.0.1") && window.location.protocol !== "file:") {
    return defaultApiBase;
  }

  return savedApiBase || defaultApiBase;
}

function formatApiError(detail) {
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (!item || typeof item !== "object") return String(item);

        const field = Array.isArray(item.loc) ? item.loc.filter((part) => part !== "body").join(".") : "";
        return field ? `${field}：${item.msg || JSON.stringify(item)}` : item.msg || JSON.stringify(item);
      })
      .join("\n");
  }

  if (detail && typeof detail === "object") {
    return detail.message || detail.msg || JSON.stringify(detail);
  }

  return detail || "";
}

const DateField = {
  props: {
    id: {
      type: String,
      default: ""
    },
    modelValue: {
      type: String,
      default: ""
    }
  },
  emits: ["update:modelValue"],
  data() {
    const initialDate = parseDateText(this.modelValue) || new Date();

    return {
      open: false,
      viewYear: initialDate.getFullYear(),
      viewMonth: initialDate.getMonth()
    };
  },
  computed: {
    monthTitle() {
      return `${this.viewYear}年${this.viewMonth + 1}月`;
    },
    selectedText() {
      return this.modelValue || "请选择日期";
    },
    calendarDays() {
      const firstDay = new Date(this.viewYear, this.viewMonth, 1);
      const start = new Date(this.viewYear, this.viewMonth, 1 - firstDay.getDay());

      return Array.from({ length: 42 }, (_, index) => {
        const date = new Date(start);
        date.setDate(start.getDate() + index);
        const text = formatDateText(date);

        return {
          text,
          day: date.getDate(),
          inMonth: date.getMonth() === this.viewMonth,
          isToday: text === todayText(),
          isSelected: text === this.modelValue
        };
      });
    }
  },
  watch: {
    modelValue(value) {
      if (!this.open) this.setViewFromValue(value);
    }
  },
  mounted() {
    document.addEventListener("pointerdown", this.closeOnOutsidePointer);
  },
  beforeUnmount() {
    document.removeEventListener("pointerdown", this.closeOnOutsidePointer);
  },
  methods: {
    setViewFromValue(value) {
      const date = parseDateText(value);
      if (!date) return;

      this.viewYear = date.getFullYear();
      this.viewMonth = date.getMonth();
    },
    togglePicker() {
      if (!this.open) this.setViewFromValue(this.modelValue);
      this.open = !this.open;
    },
    closePicker() {
      this.open = false;
    },
    closeOnOutsidePointer(event) {
      if (!this.$el.contains(event.target)) this.closePicker();
    },
    moveMonth(delta) {
      const next = new Date(this.viewYear, this.viewMonth + delta, 1);
      this.viewYear = next.getFullYear();
      this.viewMonth = next.getMonth();
    },
    selectDate(value) {
      this.$emit("update:modelValue", value);
      this.closePicker();
    }
  },
  template: `
    <div class="date-field">
      <button
        :id="id"
        class="control date-trigger"
        type="button"
        :class="{ placeholder: !modelValue }"
        @click="togglePicker"
      >
        <span>{{ selectedText }}</span>
        <span class="date-icon" aria-hidden="true">▾</span>
      </button>

      <div v-if="open" class="date-popover" @pointerdown.stop>
        <div class="date-picker-head">
          <button class="date-nav" type="button" aria-label="上个月" @click="moveMonth(-1)">‹</button>
          <strong>{{ monthTitle }}</strong>
          <button class="date-nav" type="button" aria-label="下个月" @click="moveMonth(1)">›</button>
        </div>

        <div class="date-weekdays">
          <span>日</span>
          <span>一</span>
          <span>二</span>
          <span>三</span>
          <span>四</span>
          <span>五</span>
          <span>六</span>
        </div>

        <div class="date-days">
          <button
            v-for="day in calendarDays"
            :key="day.text"
            class="date-day"
            type="button"
            :class="{ muted: !day.inMonth, today: day.isToday, selected: day.isSelected }"
            @click="selectDate(day.text)"
          >
            {{ day.day }}
          </button>
        </div>
      </div>
    </div>
  `
};

createApp({
  components: {
    DateField
  },
  data() {
    const today = todayText();

    return {
      defaultApiBase: window.location.protocol === "file:" ? "http://127.0.0.1:8000" : window.location.origin,
      apiBase: getApiBase(),
      orderTypeOptions: ORDER_TYPES,
      formTypeOptions: FORM_TYPES,
      submitting: false,
      updating: false,
      querying: false,
      receiptLoading: false,
      receiptModalOpen: false,
      deletingKey: "",
      orderMessage: { type: "info", text: "" },
      queryMessage: { type: "info", text: "" },
      receiptMessage: { type: "info", text: "" },
      orderForm: {
        user_name: "",
        start_date: today,
        end_date: today,
        order_type: ORDER_TYPES[0].value,
        form_type: "",
        remark: "",
        operator: ""
      },
      defaultOperator: "",
      queryUser: "",
      queryStartDate: today,
      queryEndDate: today,
      orders: [],
      receiptRows: [],
      currentPage: 1,
      pageSize: 10
    };
  },
  computed: {
    normalizedOrders() {
      return this.orders.map((row, index) => {
        const values = Array.isArray(row)
          ? row
          : [row.RiQi, row.XingShi, row.LeiXing, row.CNUN, row.BaoMingShiJian, row.YongHu];
        const date = this.formatDate(values[0]);

        return {
          key: `${date}-${values[5] || this.queryUser || ""}-${values[2] || ""}-${index}`,
          date,
          userName: values[5] || this.queryUser || "",
          formType: this.toDisplayText(values[1]),
          orderType: this.toDisplayText(values[2]),
          operator: values[3] || "",
          createdAt: this.formatDateTime(values[4])
        };
      });
    },
    totalPages() {
      return Math.max(1, Math.ceil(this.normalizedOrders.length / this.pageSize));
    },
    pagedOrders() {
      const start = (this.currentPage - 1) * this.pageSize;
      return this.normalizedOrders.slice(start, start + this.pageSize);
    },
    receiptColumns() {
      return ["\u65e5\u671f", "\u5730\u70b9", "\u9910\u522b", "\u83dc\u540d"];
    },
    normalizedReceiptRows() {
      return this.receiptRows.map((row) => {
        if (Array.isArray(row)) {
          return this.receiptColumns.map((_, index) => this.formatReceiptValue(row[index]));
        }

        if (row && typeof row === "object") {
          return [
            this.formatReceiptValue(row.RiQi),
            this.formatReceiptValue(row.WeiZhi),
            this.formatReceiptValue(row.leibie),
            this.formatReceiptValue(row.caiming)
          ];
        }

        return [this.formatReceiptValue(row)];
      });
    }
  },
  watch: {
    apiBase(value) {
      localStorage.setItem("happyLunchApiBase", value);
    }
  },
  mounted() {
    this.initOperator();
  },
  methods: {
    initOperator() {
      const params = new URLSearchParams(window.location.search);
      const operatorFromUrl = (params.get("operator") || "").trim();
      localStorage.removeItem("happyLunchOperator");

      if (!operatorFromUrl) {
        window.location.href = this.endpoint("/feishu/login?force=true");
        return;
      }

      const activeOperator = operatorFromUrl;

      this.defaultOperator = activeOperator;
      this.orderForm.operator = activeOperator;
      this.orderForm.user_name = this.orderForm.user_name || activeOperator;
      this.queryUser = this.queryUser || activeOperator;

      if (operatorFromUrl) {
        params.delete("operator");
        const query = params.toString();
        const cleanUrl = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
        window.history.replaceState({}, document.title, cleanUrl);
      }
    },
    endpoint(path) {
      return `${this.apiBase.replace(/\/$/, "")}${path}`;
    },
    setMessage(target, type, text) {
      this[target] = { type, text };
    },
    validateOrder() {
      if (!this.orderForm.user_name) return "请填写订餐人。";
      if (!this.orderForm.operator) return "未获取到登录用户，请重新从飞书入口进入。";
      if (!this.orderForm.start_date || !this.orderForm.end_date) return "请选择开始日期和结束日期。";
      if (this.orderForm.end_date < this.orderForm.start_date) return "结束日期不能早于开始日期。";
      if (!this.orderForm.form_type) return "请选择订餐形式。";
      return "";
    },
    validateUpdateOrder() {
      if (!this.orderForm.user_name) return "请填写订餐人。";
      if (!this.orderForm.operator) return "未获取到登录用户，请重新从飞书入口进入。";
      if (!this.orderForm.start_date || !this.orderForm.end_date) return "请选择要修改的开始日期和结束日期。";
      if (this.orderForm.end_date < this.orderForm.start_date) return "结束日期不能早于开始日期。";
      if (!this.orderForm.order_type) return "请选择餐别。";
      if (!this.orderForm.form_type) return "请选择新的订餐形式。";
      return "";
    },
    async request(path, options = {}) {
      const response = await fetch(this.endpoint(path), {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options
      });
      const contentType = response.headers.get("content-type") || "";
      const data = contentType.includes("application/json") ? await response.json() : await response.text();

      if (!response.ok) {
        const detail = data && typeof data === "object" ? data.detail : data;
        throw new Error(formatApiError(detail) || `请求失败：${response.status}`);
      }

      return data;
    },
    async submitOrder() {
      const error = this.validateOrder();
      if (error) {
        this.setMessage("orderMessage", "error", error);
        return;
      }

      this.submitting = true;
      this.setMessage("orderMessage", "info", "");

      try {
        const result = await this.request("/submit_order", {
          method: "POST",
          body: JSON.stringify(this.orderForm)
        });
        const lines = [
          result.msg || "提交完成",
          `新增日期：${(result.inserted_dates || []).join("、") || "无"}`,
          `代订通知：${result.notification_sent ? "已发送" : "未触发"}`
        ];

        if (result.duplicate_messages && result.duplicate_messages.length) {
          lines.push("重复记录：");
          lines.push(...result.duplicate_messages.map((message) => `- ${message}`));
        }

        this.setMessage("orderMessage", "success", lines.join("\n"));
      } catch (err) {
        this.setMessage("orderMessage", "error", err.message);
      } finally {
        this.submitting = false;
      }
    },
    async updateOrder() {
      const error = this.validateUpdateOrder();
      if (error) {
        this.setMessage("orderMessage", "error", error);
        return;
      }

      this.updating = true;
      this.setMessage("orderMessage", "info", "");

      try {
        const result = await this.request("/update_order", {
          method: "POST",
          body: JSON.stringify({
            user_name: this.orderForm.user_name,
            start_date: this.orderForm.start_date,
            end_date: this.orderForm.end_date,
            order_type: this.orderForm.order_type,
            form_type: this.orderForm.form_type,
            operator: this.orderForm.operator
          })
        });

        const lines = [
          result.message || "修改成功",
          `修改数量：${result.updated_count || 0}`,
          `代修改通知：${result.notification_sent ? "已发送" : "未触发"}`
        ];
        if (result.missing_dates && result.missing_dates.length) {
          lines.push(`未找到订单日期：${result.missing_dates.join("、")}`);
        }
        this.setMessage("orderMessage", "success", lines.join("\n"));

        if (this.queryUser === this.orderForm.user_name) {
          await this.checkOrder();
        }
      } catch (err) {
        this.setMessage("orderMessage", "error", err.message);
      } finally {
        this.updating = false;
      }
    },
    async checkOrder() {
      const hasStartDate = Boolean(this.queryStartDate);
      const hasEndDate = Boolean(this.queryEndDate);

      if (!this.queryUser && !hasStartDate && !hasEndDate) {
        this.setMessage("queryMessage", "error", "请输入查询人，或同时选择开始日期和结束日期。");
        return;
      }
      if (hasStartDate !== hasEndDate) {
        this.setMessage("queryMessage", "error", "开始日期和结束日期需要同时填写。");
        return;
      }
      if (hasStartDate && this.queryEndDate < this.queryStartDate) {
        this.setMessage("queryMessage", "error", "结束日期不能早于开始日期。");
        return;
      }

      const params = new URLSearchParams();
      if (this.queryUser) params.set("user_name", this.queryUser);
      if (hasStartDate) {
        params.set("start_date", this.queryStartDate);
        params.set("end_date", this.queryEndDate);
      }

      this.querying = true;
      this.setMessage("queryMessage", "info", "");

      try {
        const result = await this.request(`/check_order?${params.toString()}`, {
          method: "GET",
          headers: {}
        });
        this.orders = Array.isArray(result) ? result : [];
        this.currentPage = 1;
        this.setMessage("queryMessage", "success", `查询完成，共 ${this.orders.length} 条记录。`);
      } catch (err) {
        this.orders = [];
        this.currentPage = 1;
        this.setMessage("queryMessage", "error", err.message);
      } finally {
        this.querying = false;
      }
    },
    async showTodayReceipt() {
      this.receiptModalOpen = true;
      this.receiptLoading = true;
      this.receiptRows = [];
      this.receiptMessage = { type: "info", text: "" };

      try {
        const result = await this.request("/get_receipt", {
          method: "GET",
          headers: {}
        });
        const rows = result && Array.isArray(result.rows)
          ? result.rows
          : Array.isArray(result)
            ? result
            : result
              ? [result]
              : [];

        this.receiptRows = rows;
        if (!rows.length) {
          this.receiptMessage = { type: "info", text: "今日暂无菜单。" };
        }
      } catch (err) {
        this.receiptMessage = { type: "error", text: err.message };
      } finally {
        this.receiptLoading = false;
      }
    },
    closeReceiptModal() {
      if (!this.receiptLoading) {
        this.receiptModalOpen = false;
      }
    },
    async deleteOrder(item) {
      const operator = this.orderForm.operator || this.defaultOperator;
      const userName = item.userName || this.queryUser;

      if (!operator) {
        this.setMessage("queryMessage", "error", "未获取到登录用户，请重新从飞书入口进入。");
        return;
      }
      if (!userName) {
        this.setMessage("queryMessage", "error", "未获取到要取消的订餐人。");
        return;
      }

      this.deletingKey = item.key;

      try {
        const result = await this.request("/delete_order", {
          method: "POST",
          body: JSON.stringify({
            user_name: userName,
            start_date: item.date,
            order_type: item.orderType,
            operator
          })
        });
        this.setMessage("queryMessage", "success", result.message || "取消成功");
        await this.checkOrder();
      } catch (err) {
        this.setMessage("queryMessage", "error", err.message);
      } finally {
        this.deletingKey = "";
      }
    },
    goToPage(page) {
      const nextPage = Math.min(Math.max(Number(page) || 1, 1), this.totalPages);
      this.currentPage = nextPage;
    },
    goToLastPage() {
      this.goToPage(this.totalPages);
    },
    resetOrder() {
      const today = todayText();
      this.queryUser = this.defaultOperator;
      this.queryStartDate = today;
      this.queryEndDate = today;
      this.orderForm = {
        user_name: this.defaultOperator,
        start_date: today,
        end_date: today,
        order_type: ORDER_TYPES[0].value,
        form_type: "",
        remark: "",
        operator: this.defaultOperator
      };
      this.orderMessage = { type: "info", text: "" };
    },
    setEndDateToNextFriday() {
      if (!this.orderForm.start_date) return;

      const start = new Date(`${this.orderForm.start_date}T00:00:00`);
      const friday = 5;
      let daysUntilFriday = (friday - start.getDay() + 7) % 7;

      if (daysUntilFriday === 0) {
        daysUntilFriday = 7;
      }

      start.setDate(start.getDate() + daysUntilFriday);
      this.orderForm.end_date = this.formatDate(start);
    },
    toDisplayText(value) {
      return DISPLAY_TEXT.get(value) || value || "";
    },
    formatDate(value) {
      if (!value) return "";
      if (typeof value === "string") return value.slice(0, 10);

      const date = value instanceof Date ? value : new Date(value);
      return formatDateText(date);
    },
    formatDateTime(value) {
      if (!value) return "";
      if (typeof value === "string") return value.replace("T", " ").slice(0, 19);
      return new Date(value).toLocaleString("zh-CN", { hour12: false });
    },
    formatReceiptValue(value) {
      if (value === null || value === undefined) return "";
      if (typeof value === "string") return value.replace("T", " ").slice(0, 19);
      if (typeof value === "number" || typeof value === "boolean") return String(value);
      return JSON.stringify(value);
    }
  }
}).mount("#app");
