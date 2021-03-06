## CC视频流下载器

监视&自动下载工具。适用场景是，比如切片哥出于某种目的需要获取直播视频流（比如认为上传视频的码率没有直播高，或者需要切片未上传的录播等）的时候，自己没有时间24小时盯着直播的情况。可以事前开启这个工具，它会在开播后自动下载流。

监视数字id由watch_id.txt控制，默认是为361433。

下载的文件由很多个视频流文件组成。直播结束后将其中任意一个拖入merge.cmd合并为一个视频文件，会自动进行排序。

### 面向0基础的一些额外的说明

科普一些技术方面的内容，以及介绍使用脚本下载的优势有几点

- 首先当然是可以无人值守，不用守在电脑前了。
- 然后是画质要高一些，录屏软件的画质损失主要来自于两个方面，其一是为了达成流编码，也就是捕捉一个流的同时将它压制成视频文件，通常录像软件会选择追求效率的编码器，比如nvenc。虽然现代编码器本身都不弱，不会出现乍一看就差很多的情况，但是从严格画质对比的角度相比于x265--slow之类的慢处理编码器来说其实确实劣化了很多。主播那边推流时本身就进行了一次类似的压缩，然后录播哥这边又压缩了一遍。另外一个影响画质的来源是弹幕的录制，因为字体这种细节上有棱有角的东西，其实与编码器基于宏块的压缩原理蛮冲突的。也就是说假如你有精力做一个对比实验，比如录像输出码率给到8000，满屏弹幕和没有弹幕的同一段视频比，用分析软件放大看看细节，会发现弹幕版的细节画质差很多，因为码率被汉字吃掉了。当然了录播还有帧率不稳之类的问题，不一而足，这里不再赘述，总之如果对画质有追求的话，录像是比较糟糕的选择。
- 还有就是不用担心流卡顿的问题了，自己观看视频的话，不知道各位如何，我看直播时偶尔会卡顿。这与网络环境的间断性丢包有关，除非是特别优质的网络线路，否则一般很难避免这种情况的发生。而我们不太了解cc网页版具体是怎么实现的直播流下载，比如是单线程还是多线程之类的，因此时有卡顿发生。使用脚本下载的好处是它不需要播放，所以下载本身是多线程乱序完成的，可以更充分地利用带宽，也不会担心播到一半卡了，反正都是后期合成的。只要不出现严重的网络停顿，比如三十秒内封包全部丢失，普通家用网络的丢包率可以保证流畅。
- 缺点是弹幕没有了，不过既然弹幕有服务记录倒是也有很多办法还原，这点不再赘述，不过可能是需要额外花费一些压制时间。

总之作为总结，这是一个花费时间换取效率的工具，你的电脑需要工作更长时间，换来的是人可以轻松一些，还有就是录播的画质稍高一些。
