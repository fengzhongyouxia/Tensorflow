# -*- coding: UTF-8 -*-

from __future__ import print_function
import numpy as np
import pickle
import os
from os import path
import zlib
import gzip
import gdal
import sys
# import cv2
import datetime
import tensorflow as tf


start_time = datetime.datetime.now()
print("startTime: ", start_time)

def create_pickle_train(image_path, mask_path, img_pixel=9, channels=4):
    m = 0

    image_data = Multiband2Array(image_path)
    print("data_matrix_max= ", image_data.max())
    print("data_matrix_min= ", image_data.min())
    # mask_data = cv2.split(cv2.imread(mask_path))[0] / 255
    mask_data=Multiband2Array(mask_path)/255

    x_size, y_size = image_data.shape[:2]

    data_list = []

    for i in range(0, x_size - img_pixel + 1, img_pixel // 2):  # 文件夹下的文件名
        if i + img_pixel > x_size:
            i = x_size - img_pixel - 1
        for j in range(0, y_size - img_pixel + 1, img_pixel // 2):
            if j + img_pixel > y_size:
                j = y_size - img_pixel - 1
            cropped_data = image_data[i:i + img_pixel, j:j + img_pixel]
            data1 = cropped_data.reshape((-1, img_pixel * img_pixel * channels))  # 展成一行
            train_label = mask_data[i+img_pixel//2,j+img_pixel//2]
            data2 = np.append(data1, train_label)[np.newaxis, :]  # 数据+标签

            data_list.append(data2)

            m += 1

            if m % 10000 == 0:
                print(datetime.datetime.now(), "compressed {number} images".format(number=m))
                data_matrix = np.array(data_list, dtype=int)

                data_matrix = data_matrix.reshape((-1, (img_pixel * img_pixel * channels + 1)))
                return data_matrix

    print(len(data_list))
    print(m)

    data_matrix = np.array(data_list, dtype=int)

    data_matrix = data_matrix.reshape((-1, (img_pixel * img_pixel * channels+1)))

    """
    with gzip.open('D:/train_data_64.pkl', 'ab') as writer:  # 以压缩包方式创建文件，进一步压缩文件
        pickle.dump(data_matrix, writer)  # 数据存储成pickle文件
    """
    return data_matrix # shape [none,9*9*4+1]

def Multiband2Array(path):

    src_ds = gdal.Open(path)
    if src_ds is None:
        print('Unable to open %s'% path)
        sys.exit(1)

    xcount=src_ds.RasterXSize # 宽度
    ycount=src_ds.RasterYSize # 高度
    ibands=src_ds.RasterCount # 波段数

    # print "[ RASTER BAND COUNT ]: ", ibands
    # if ibands==4:ibands=3
    for band in range(ibands):
        band += 1
        # print "[ GETTING BAND ]: ", band
        srcband = src_ds.GetRasterBand(band) # 获取该波段
        if srcband is None:
            continue

        # Read raster as arrays 类似RasterIO（C++）
        dataraster = srcband.ReadAsArray(0, 0, xcount, ycount).astype(np.float16)
        if band==1:
            data=dataraster.reshape((ycount,xcount,1))
        else:
            # 将每个波段的数组很并到一个3维数组中
            data=np.append(data,dataraster.reshape((ycount,xcount,1)),axis=2)

    return data

def next_batch(data, batch_size, flag, img_pixel=3, channels=4):
    global start_index  # 必须定义成全局变量
    global second_index  # 必须定义成全局变量

    if 1==flag:
        start_index = 0
    # start_index = 0
    second_index = start_index + batch_size

    if second_index > len(data):
        second_index = len(data)

    data1 = data[start_index:second_index]
    # print('start_index', start_index, 'second_index', second_index)

    start_index = second_index
    if start_index >= len(data):
        start_index = 0

    # 将每次得到batch_size个数据按行打乱
    index = [i for i in range(len(data1))]  # len(data1)得到的行数
    np.random.shuffle(index)  # 将索引打乱
    data1 = data1[index]

    # 提取出数据和标签
    img = data1[:, 0:img_pixel * img_pixel * channels]

    # img = img * (1. / img.max) - 0.5
    img = img * (1. / 255) - 0.5  # 数据归一化到 -0.5～0.5
    img = img.astype(np.float32)  # 类型转换

    label = data1[:, -1]
    label = label.astype(int)  # 类型转换

    return img, label

def dense_to_one_hot(labels_dense, num_classes):
    """Convert class labels from scalars to one-hot vectors."""
    # 从标量类标签转换为一个one-hot向量
    num_labels = labels_dense.shape[0]        #label的行数
    index_offset = np.arange(num_labels) * num_classes
    # print index_offset
    labels_one_hot = np.zeros((num_labels, num_classes))
    labels_one_hot.flat[index_offset + labels_dense.ravel()] = 1
    return labels_one_hot

# ---------------------------------------------#
image_path = r"E:\项目\AI-Waterdetection-PL-4band\train_data\train_img_01.tif"
mask_path = r"E:\项目\AI-Waterdetection-PL-4band\train_data\train_img_mask_01.tif"
data=create_pickle_train(image_path, mask_path, img_pixel=9, channels=4)
isize = 9
img_channel = 4
img_pixel = isize
model_save_path = r"./model2/"

# Parameters
training_epochs = 2
batch_size = 100

display_step = 1
channels = img_channel

# Network Parameters
img_size = isize * isize * channels
label_cols = 2
dropout = 0.75
img_nums = data.shape[0]
print(img_nums)
# -------------------------------------------------------------#

# ---------设置动态学习效率
# Constants describing the training process.
# MOVING_AVERAGE_DECAY = 0.9999     # The decay to use for the moving average.
NUM_EPOCHS_PER_DECAY = batch_size  # Epochs after which learning rate decays.
LEARNING_RATE_DECAY_FACTOR = 0.95  # Learning rate decay factor.
INITIAL_LEARNING_RATE = 0.001  # Initial learning rate.
global_step = tf.Variable(0)

# global_step = training_epochs * (img_nums // batch_size)  # Integer Variable counting the number of training steps     # //是整数除法
# Variables that affect learning rate.
num_batches_per_epoch = int(img_nums / batch_size)
# decay_steps = int(num_batches_per_epoch * NUM_EPOCHS_PER_DECAY)
decay_steps = int(num_batches_per_epoch * 10)
# decay_steps = int(2)
# Decay the learning rate exponentially based on the number of steps.
learning_rate = tf.train.exponential_decay(INITIAL_LEARNING_RATE,
                                           global_step,
                                           decay_steps,
                                           LEARNING_RATE_DECAY_FACTOR,
                                           staircase=True)

# tf Graph Input
x = tf.placeholder(tf.float32, [None, img_size])  # mnist data image of shape 28*28=784
y = tf.placeholder(tf.float32, [None, label_cols])  #
keep_prob = tf.placeholder(tf.float32)  # dropout (keep probability)


# Create some wrappers for simplicity
def conv2d(x, W, b, strides=1):
    # Conv2D wrapper, with bias and relu activation
    x = tf.nn.conv2d(x, W, strides=[1, strides, strides, 1], padding='SAME')
    x = tf.nn.bias_add(x, b)  # strides中间两个为1 表示x,y方向都不间隔取样
    return tf.nn.relu(x)


def maxpool2d(x, k=2):
    # MaxPool2D wrapper
    return tf.nn.max_pool(x, ksize=[1, k, k, 1], strides=[1, k, k, 1],
                          padding='SAME')  # strides中间两个为2 表示x,y方向都间隔1个取样


# Create model
def conv_net(x, weights, biases, dropout):
    # Reshape input picture
    x = tf.reshape(x, shape=[-1, img_pixel, img_pixel, channels])  # 9x9x4

    # Convolution Layer
    conv1 = conv2d(x, weights['wc1'], biases['bc1'])  # 图像9x9x64
    # Max Pooling (down-sampling)
    conv1 = maxpool2d(conv1, k=2)  # 图像 5x5x64

    # Convolution Layer
    conv2 = conv2d(conv1, weights['wc2'], biases['bc2'])  # 图像 5x5x128
    # Max Pooling (down-sampling)
    conv2 = maxpool2d(conv2, k=2)  # 图像 3x3x128

    # Convolution Layer
    # conv3 = conv2d(conv2, weights['wc3'], biases['bc3'])  # 图像 3x3x256
    # Max Pooling (down-sampling)
    # conv3 = maxpool2d(conv3, k=2)  # 图像 2x2x256

    # Fully connected layer
    # Reshape conv2 output to fit fully connected layer input
    fc1 = tf.reshape(conv2, [-1, weights['wd1'].get_shape().as_list()[0]])  # [None,2*2*256]-->[None,1024]
    fc1 = tf.add(tf.matmul(fc1, weights['wd1']), biases['bd1'])
    fc1 = tf.nn.relu(fc1)
    # Apply Dropout
    fc1 = tf.nn.dropout(fc1, dropout)

    # Output, class prediction
    out = tf.add(tf.matmul(fc1, weights['out']), biases['out'])
    return out

# Store layers weight & bias
weights = {
    # 5x5 conv, 3 input, 32 outputs 彩色图像3个输入(3个频道)，灰度图像1个输入
    'wc1': tf.Variable(tf.random_normal([5, 5, channels, 64])),  # 5X5的卷积模板   #tf.random_normal是从正态分布中输出随机数
    # 5x5 conv, 32 inputs, 64 outputs
    'wc2': tf.Variable(tf.random_normal([5, 5, 64, 128])),
    # 5x5 conv, 128 inputs, 128 outputs
    # 'wc3': tf.Variable(tf.random_normal([5, 5, 128, 256])),
    # fully connected, 7*7*64 inputs, 1024 outputs
    'wd1': tf.Variable(tf.random_normal([(1+img_pixel // 4) * (1+img_pixel // 4) * 128, 1024])),
    # 1024 inputs, 10 outputs (class prediction)
    'out': tf.Variable(tf.random_normal([1024, label_cols]))
}

biases = {
    'bc1': tf.Variable(tf.random_normal([64])),
    'bc2': tf.Variable(tf.random_normal([128])),
    # 'bc3': tf.Variable(tf.random_normal([256])),
    'bd1': tf.Variable(tf.random_normal([1024])),
    'out': tf.Variable(tf.random_normal([label_cols]))
}

# Construct model
pred = conv_net(x, weights, biases, keep_prob)

# Define loss and optimizer
cost = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(labels=y, logits=pred))
optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate).minimize(cost, global_step=global_step)

# Evaluate model
correct_pred = tf.equal(tf.argmax(pred, 1), tf.argmax(y, 1))
accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))

# 初始化所有的op
init = tf.global_variables_initializer()


if __name__ == '__main__':

    if not os.path.isdir(model_save_path):
        os.makedirs(model_save_path)  # 创建输出文件目录
    model_fn = path.join(model_save_path, 'save_net.ckpt')


    saver = tf.train.Saver()  # 默认是保存所有变量

    with tf.Session(config=tf.ConfigProto(log_device_placement=False)) as sess:
        sess.run(init)

        # 验证之前是否已经保存了检查点文件
        ckpt = tf.train.get_checkpoint_state(model_save_path)
        if ckpt and ckpt.model_checkpoint_path:
            saver.restore(sess, ckpt.model_checkpoint_path)
            print("提取现有模型训练")

        total_batch = int(img_nums / batch_size)
        learning_rate_me = 0
        lrc = 0.0

        for epoch in range(training_epochs):
            np.random.shuffle(data)

            avg_cost = 0.
            flag = 1

            for i in range(total_batch):
                img, label = next_batch(data, batch_size, flag, img_pixel=isize, channels=img_channel)
                flag = 0
                batch_xs = img.reshape([-1, img_size])

                batch_ys = dense_to_one_hot(label[:, np.newaxis], label_cols)  # 生成多列标签   问题6，生成多列标签是干什么呢？   by xjxf
                # Run optimization op (backprop) and cost op (to get loss value)
                _, c, p,gl_step = sess.run([optimizer, cost, pred,global_step], feed_dict={x: batch_xs,
                                                              y: batch_ys, keep_prob: dropout})

                if i%10==0:print('global_step',gl_step,'cost',c)
                # Compute average loss
                avg_cost += c / total_batch
                learning_rate_me=sess.run(learning_rate)
                if learning_rate_me!=lrc:
                    lrc=learning_rate_me
                    print("learning_rate:",str(learning_rate_me))

            # Display logs per epoch step
            if (epoch + 1) % display_step == 0:
                print("time: ", datetime.datetime.now())
                print("Epoch:", '%04d' % (epoch + 1),
                      "cost:", "{:.9f}".format(avg_cost),
                      'accuracy:', sess.run(accuracy, feed_dict={x: batch_xs, y: batch_ys, keep_prob: 1.0}))
                save_path = saver.save(sess, model_fn)  # model_fn 路径中不能出现中文否则会报错
                print('Saver path:', save_path)
                print("模型保存完毕！")
        print("Optimization Finished!")

        end_time = datetime.datetime.now()
        print("end_time: ", end_time)
        print("time used: ", end_time-start_time)
