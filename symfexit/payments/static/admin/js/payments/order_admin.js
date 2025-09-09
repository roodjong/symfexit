'use strict';
{
  const $ = django.jQuery;
  let initialValuesMap = {};

  async function loadProductInfo(selector) {
    const $this = $(selector);
    const scriptEl = document.getElementById('load-product-script');
    const baseUrl = scriptEl.dataset.loadProductBaseUrl;

    if ($this.val() === '') {
      return;
    }
    const productId = $this.val();
    const resp = await fetch(`${baseUrl}/${productId}`);
    const data = await resp.json();
    for (const [key, value] of Object.entries(data)) {
      if ($(`#id_${key}`).val() && initialValuesMap[`id_${key}`] !== $(`#id_${key}`).val()) {
        continue;
      }
      $(`#id_${key}`).val(value);
      initialValuesMap[`id_${key}`] = $(`#id_${key}`).val();
    }
  }

  function el(tagName, attrs, children = null) {
    let node = document.createElement(tagName);
    for (const [key, value] of Object.entries(attrs)) {
      node.setAttribute(key, value);
    }
    if (children === null) {
      // No children
    } else if (typeof (children) === "string") {
      node.appendChild(document.createTextNode(children));
    } else if (children.length) {
      for (const element of children) {
        node.appendChild(element);
      }
    } else {
      node.appendChild(children);
    }
    return node;
  }

  async function autoAddAddress(e) {
    e.preventDefault();
    const select = $('.related-widget-wrapper select#id_ordered_for');
    const scriptEl = document.getElementById('load-product-script');
    const baseUrl = scriptEl.dataset.autoAddBaseUrl;

    const billingAddressSelect = $('.related-widget-wrapper select#id_ordered_for_billing_address');

    if (!select.val()) {
      return;
    }

    const resp = await fetch(`${baseUrl}/${select.val()}`);
    const data = await resp.json();
    if (data["billing_address_id"]) {
      let option = new Option(data["full_name"], data["billing_address_id"], true, true);
      billingAddressSelect.append(option).trigger("change");
      billingAddressSelect.trigger({
        type: 'select2:select',
        params: {
          data: data
        }
      });
    }
    if (data["message"]) {
      document.getElementById('billingaddress_errorlist').appendChild(el("li", { class: "errornote" }, data["message"]))
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    $('.related-widget-wrapper select#id_product').on("django:update-related", function (e) {
      loadProductInfo(this);
    });

    $('#order_form :input').each(function (index) {
      if (!this.id) return;
      initialValuesMap[this.id] = $(this).val();
    });
    const billingAddressContainer = document.querySelector('[data-model-ref="billingaddress"]');
    const addRelatedLink = billingAddressContainer.querySelector('.related-widget-wrapper-link.add-related');
    const autoAddLink = el('a', { title: "Automatically add address from user", href: "#", class: "related-widget-wrapper-link" }, "Auto add");
    autoAddLink.addEventListener("click", (e) => autoAddAddress(e));
    billingAddressContainer.insertBefore(autoAddLink, addRelatedLink);

    const errorList = document.querySelector('.related-widget-wrapper[data-model-ref="billingaddress"]').appendChild(el("ul", { id: "billingaddress_errorlist", class: "errorlist" }));

    $('.related-widget-wrapper select#id_ordered_for_billing_address').on("django:update-related", function (e) {
      errorList.innerHTML = '';
    });

    $('.related-widget-wrapper select#id_ordered_for').on("django:update-related", function (e) {
      errorList.innerHTML = '';
      if (!$(this).val()) {
        autoAddLink.ariaDisabled = true;
        autoAddLink.removeAttribute('href');
      } else {
        autoAddLink.ariaDisabled = false;
        autoAddLink.setAttribute('href', '#');
      }
    });
  });
}
