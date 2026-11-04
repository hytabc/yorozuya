<script setup>
import { RouterLink } from 'vue-router'
</script>

<template>
  <div class="page inner-page terms-page">
    <section class="section-heading">
      <div>
        <span class="section-index">TERMS</span>
        <h2>使用条款与免责声明</h2>
        <p>进入委托大厅前会先展示一屏「委托礼仪」，完整法律条款始终保留在本页。</p>
      </div>
    </section>

    <div class="disclaimer-body terms-body">
      <div class="disclaimer-part">
        <h3>一、平台性质说明</h3>
        <p>本网站仅为信息撮合平台，提供委托需求发布、志愿者接单申请的信息展示服务。平台不参与、不担保、不介入任何委托的执行、报酬交易、线下沟通。所有委托内容由发布用户自行编写，平台不对委托内容真实性、合法性做前置人工审核，违规内容依靠用户举报机制进行处理。</p>
      </div>
      <div class="disclaimer-part">
        <h3>二、关于委托</h3>
        <ol>
          <li>平台不收取任何服务费、抽成，不接收、不处理任何资金流转。委托人与志愿者之间的报酬、转账、押金等全部由双方私下自行协商完成。</li>
          <li>平台不对资金安全、交易履约做任何担保。请用户提高警惕，谨防诈骗，拒绝任何提前缴纳押金、预付款等要求。</li>
        </ol>
      </div>
      <div class="disclaimer-part">
        <h3>三、双向自愿规则</h3>
        <p>本平台委托为双向自愿配对模式。委托人、志愿者均拥有随时取消委托的权利，平台不强制任何一方履行委托。因取消委托、沟通分歧产生的纠纷，由双方自行协商解决，平台不承担调解、赔付责任。</p>
      </div>
      <div class="disclaimer-part">
        <h3>四、用户责任</h3>
        <ol>
          <li>用户注册、发布委托、申请接单，代表用户承诺所提交的信息真实合法，不得发布色情、暴力、诈骗、违法违规内容。</li>
          <li>用户在平台外私下联系沟通产生的人身、财产、名誉损害，全部由当事人自行承担，本平台不承担法律责任。</li>
        </ol>
      </div>
      <div class="disclaimer-part">
        <h3>五、举报与处置</h3>
        <ol>
          <li>若发现违规委托、违规账号，用户可使用网站举报功能提交举报。</li>
          <li>平台收到举报后，将在空闲时间对内容进行核查，有权下架违规委托、限制或封禁违规账号；但不保证100%拦截全部违规内容。</li>
        </ol>
      </div>
      <div class="disclaimer-part">
        <h3>六、法律免责</h3>
        <p>因用户自身行为导致的一切损失，本平台不承担任何民事、刑事赔偿责任。如发生法律纠纷，由当事双方通过司法途径解决。</p>
      </div>
    </div>

    <RouterLink class="text-link terms-back" to="/">返回委托大厅</RouterLink>
  </div>
</template>
