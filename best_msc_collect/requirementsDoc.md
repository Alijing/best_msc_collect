重写一个web_collect_data 工具类

1. 获取网页数据
2. 如果发现有下一页 dom 元素，则执行点击操作
3. 继续获取下一页中的数据
4. 重复1、2、3，知道找不到符合规则的 dom 元素为止
5. 从获取到的数据中，执行操作进入详情页面，获取详情数据
6. 再详情页面如果有下一页 dom 元素，则执行点击操作
7. 继续获取下一页数据
8. 重复5、6、7，知道找不到符合规则的 dom 元素为止

<div class="listmain">
	<dl>
		<dt>《烟雨楼》正文卷</dt>
		<dd><a href="/html/95794/95794064/4098049.html">第1章 天资妖孽李子夜</a></dd>
		<dd><a href="/html/95794/95794064/4098048.html">第2章 冰清玉洁秦婀娜</a></dd>
	</dl>
</div>

<div class="book reader">
	<div class="content">
		<h1>第1章 天资妖孽李子夜</h1>
		<div id="content" class="showtxt">“秦仙子要来渝州城了！”
        <br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;大商皇朝，渝州城，不知何方传来的一条消息，瞬间引爆了整座城！
        <br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;“秦仙子？那个梅花剑仙？她来渝州城做什么？”
        <br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;“当然是为了收弟子！”
        <br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;多日来，不论说书人，还是城中权贵都谈论一个人。
       </div>
</div>
</div>


